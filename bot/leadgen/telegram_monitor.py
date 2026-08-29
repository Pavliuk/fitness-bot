"""
Моніторинг публічних Telegram-груп/каналів на згадки ключових слів (лідогенерація).

Технічна причина, чому це Telethon (звичайний user-акаунт), а не Bot API:
бот, доданий через @BotFather, не може сам приєднуватись до публічних груп і
не бачить чужих чатів, куди його явно не додали як учасника/адміна. Тому
моніторинг веде окремий Telegram-акаунт (через API_ID/API_HASH з
my.telegram.org) — той самий акаунт, яким користувач сам приєднується до
потрібних публічних спільнот (наприклад, локальні дошки оголошень).

Опрацьовуються ЛИШЕ джерела зі списку LeadSource (публічні канали/групи, до
яких цей акаунт сам приєднався). Приватні діалоги/особисте листування цього
акаунта НІКОЛИ не скануються — обробник підписаний тільки на chats=[...] зі
списку активних джерел.
"""
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import async_sessionmaker
from telethon import TelegramClient, events
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

from bot.database.models import LeadPlatform
from bot.leadgen.db import get_active_keywords, get_active_sources, save_lead, set_source_chat_id

logger = logging.getLogger(__name__)

NotifyCallback = Callable[[str], Awaitable[None]]


class LeadMonitor:
    """Тримає одну Telethon-сесію, приєднується до джерел і слухає нові повідомлення в них."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_name: str,
        session_maker: async_sessionmaker,
    ) -> None:
        self._client = TelegramClient(session_name, api_id, api_hash)
        self._session_maker = session_maker
        self._notify: NotifyCallback | None = None
        self._chat_ids: set[int] = set()

    async def start(self, notify: NotifyCallback) -> None:
        self._notify = notify
        await self._client.start()
        me = await self._client.get_me()
        logger.info("Leadgen: Telegram-сесія підключена як %s", getattr(me, "username", me.id))

        await self._sync_sources()
        if not self._chat_ids:
            logger.warning(
                "Leadgen: активних джерел немає — додайте їх командою /src_add у боті "
                "й перезапустіть бота, щоб моніторинг підхопив нове джерело."
            )
            return

        # chats=self._chat_ids звужує підписку виключно до доданих публічних джерел —
        # особисті діалоги/приватне листування цього акаунта в обробник НЕ потрапляють.
        self._client.add_event_handler(self._handle_message, events.NewMessage(chats=self._chat_ids))
        logger.info("Leadgen: моніторинг %d джерел(а) запущено.", len(self._chat_ids))

    async def run_until_disconnected(self) -> None:
        await self._client.run_until_disconnected()

    async def stop(self) -> None:
        await self._client.disconnect()

    # ---------- Приєднання до джерел ----------

    async def _sync_sources(self) -> None:
        async with self._session_maker() as session:
            sources = await get_active_sources(session, platform=LeadPlatform.telegram)

        for source in sources:
            chat_id = await self._join_and_resolve(source.identifier)
            if chat_id is None:
                continue
            self._chat_ids.add(chat_id)
            async with self._session_maker() as session:
                await set_source_chat_id(session, source.id, chat_id)

    async def _join_and_resolve(self, identifier: str) -> int | None:
        try:
            if "joinchat" in identifier or "/+" in identifier:
                invite_hash = identifier.rsplit("/", 1)[-1].lstrip("+")
                updates = await self._client(ImportChatInviteRequest(invite_hash))
                chat = updates.chats[0]
            else:
                username = identifier.lstrip("@")
                updates = await self._client(JoinChannelRequest(username))
                chat = updates.chats[0]
            logger.info("Leadgen: приєднався до %s", identifier)
            return chat.id
        except UserAlreadyParticipantError:
            entity = await self._client.get_entity(identifier)
            return entity.id
        except FloodWaitError as e:
            logger.warning("Leadgen: FloodWait %s сек при приєднанні до %s", e.seconds, identifier)
        except (ChannelPrivateError, InviteHashInvalidError, InviteHashExpiredError) as e:
            logger.warning("Leadgen: не вдалося приєднатись до %s: %s", identifier, e)
        except Exception:
            logger.exception("Leadgen: помилка приєднання до %s", identifier)
        return None

    # ---------- Обробка повідомлень ----------

    async def _handle_message(self, event) -> None:
        text = (event.raw_text or "").strip()
        if not text:
            return

        async with self._session_maker() as session:
            keywords = await get_active_keywords(session)
            if not keywords:
                return
            lowered = text.lower()
            matched = next((kw for kw in keywords if kw.phrase in lowered), None)
            if matched is None:
                return

            sources = await get_active_sources(session, platform=LeadPlatform.telegram)
            source = next((s for s in sources if s.platform_chat_id == event.chat_id), None)
            if source is None:
                return

            chat = await event.get_chat()
            chat_username = getattr(chat, "username", None)
            sender = await event.get_sender()
            author_username = getattr(sender, "username", None)
            message_link = f"https://t.me/{chat_username}/{event.id}" if chat_username else None

            await save_lead(
                session,
                source_id=source.id,
                keyword_id=matched.id,
                platform_message_id=str(event.id),
                text_snippet=text,
                message_link=message_link,
                author_username=author_username,
            )

            keyword_phrase = matched.phrase
            source_label = source.title or source.identifier

        if self._notify is None:
            return
        preview = text if len(text) <= 300 else text[:300] + "…"
        who = f"@{author_username}" if author_username else "автор без публічного username"
        link_line = f"\n{message_link}" if message_link else ""
        await self._notify(
            f"🎯 Новий лід за словом «{keyword_phrase}»\n"
            f"Джерело: {source_label}\n"
            f"Автор: {who}\n"
            f"Текст: {preview}{link_line}"
        )
