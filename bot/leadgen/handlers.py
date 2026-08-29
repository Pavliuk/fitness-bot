"""Адмінські команди модуля лідогенерації.

Доступ лише для tg_id, перелічених у ADMIN_IDS (.env) — це власник бізнесу,
для якого й ведеться пошук потенційних клієнтів.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.leadgen.db import (
    add_keyword,
    add_source,
    deactivate_keyword,
    deactivate_source,
    get_active_keywords,
    get_active_sources,
    get_recent_leads,
)

router = Router(name="leadgen")

HELP_TEXT = (
    "🎯 <b>Модуль лідогенерації</b>\n"
    "Шукає публічні згадки ваших ключових слів у публічних Telegram-групах/"
    "каналах, до яких приєднаний акаунт-монітор.\n\n"
    "<b>Ключові слова</b>\n"
    "/kw_add &lt;фраза&gt; — додати\n"
    "/kw_list — список активних\n"
    "/kw_del &lt;id&gt; — вимкнути\n\n"
    "<b>Джерела (публічні групи/канали)</b>\n"
    "/src_add &lt;@username або посилання-запрошення&gt; — додати\n"
    "/src_list — список активних\n"
    "/src_del &lt;id&gt; — вимкнути\n"
    "⚠️ Після /src_add потрібен перезапуск бота, щоб моніторинг підхопив нове джерело.\n\n"
    "<b>Ліди</b>\n"
    "/leads [N] — останні N знайдених лідів (за замовчуванням 10)"
)


def _is_admin(message: Message, admin_ids: list[int]) -> bool:
    return message.from_user is not None and message.from_user.id in admin_ids


@router.message(Command("start"))
@router.message(Command("leads_help"))
async def cmd_help(message: Message, admin_ids: list[int]):
    if not _is_admin(message, admin_ids):
        return
    await message.answer(HELP_TEXT)


@router.message(Command("kw_add"))
async def cmd_kw_add(message: Message, admin_ids: list[int], session_maker: async_sessionmaker):
    if not _is_admin(message, admin_ids):
        return
    phrase = (message.text or "").split(maxsplit=1)
    if len(phrase) < 2:
        await message.answer("Формат: /kw_add фраза")
        return
    async with session_maker() as session:
        keyword = await add_keyword(session, phrase[1])
    if keyword is None:
        await message.answer("Порожня фраза — не додано.")
        return
    await message.answer(f"✅ Додано ключове слово #{keyword.id}: «{keyword.phrase}»")


@router.message(Command("kw_list"))
async def cmd_kw_list(message: Message, admin_ids: list[int], session_maker: async_sessionmaker):
    if not _is_admin(message, admin_ids):
        return
    async with session_maker() as session:
        keywords = await get_active_keywords(session)
    if not keywords:
        await message.answer("Список ключових слів порожній.")
        return
    lines = [f"#{kw.id} — {kw.phrase}" for kw in keywords]
    await message.answer("<b>Активні ключові слова:</b>\n" + "\n".join(lines))


@router.message(Command("kw_del"))
async def cmd_kw_del(message: Message, admin_ids: list[int], session_maker: async_sessionmaker):
    if not _is_admin(message, admin_ids):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Формат: /kw_del id")
        return
    async with session_maker() as session:
        ok = await deactivate_keyword(session, int(parts[1]))
    await message.answer("✅ Вимкнено." if ok else "Не знайдено таке id.")


@router.message(Command("src_add"))
async def cmd_src_add(message: Message, admin_ids: list[int], session_maker: async_sessionmaker):
    if not _is_admin(message, admin_ids):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /src_add @username_або_посилання")
        return
    async with session_maker() as session:
        source = await add_source(session, parts[1])
    await message.answer(
        f"✅ Додано джерело #{source.id}: {source.identifier}\n"
        "⚠️ Перезапустіть бота, щоб моніторинг приєднався до нього."
    )


@router.message(Command("src_list"))
async def cmd_src_list(message: Message, admin_ids: list[int], session_maker: async_sessionmaker):
    if not _is_admin(message, admin_ids):
        return
    async with session_maker() as session:
        sources = await get_active_sources(session)
    if not sources:
        await message.answer("Список джерел порожній.")
        return
    lines = [f"#{s.id} — {s.title or s.identifier} ({s.platform.value})" for s in sources]
    await message.answer("<b>Активні джерела:</b>\n" + "\n".join(lines))


@router.message(Command("src_del"))
async def cmd_src_del(message: Message, admin_ids: list[int], session_maker: async_sessionmaker):
    if not _is_admin(message, admin_ids):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Формат: /src_del id")
        return
    async with session_maker() as session:
        ok = await deactivate_source(session, int(parts[1]))
    await message.answer("✅ Вимкнено." if ok else "Не знайдено таке id.")


@router.message(Command("leads"))
async def cmd_leads(message: Message, admin_ids: list[int], session_maker: async_sessionmaker):
    if not _is_admin(message, admin_ids):
        return
    parts = (message.text or "").split()
    limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
    async with session_maker() as session:
        leads = await get_recent_leads(session, limit=limit)
    if not leads:
        await message.answer("Поки що лідів не знайдено.")
        return
    blocks = []
    for lead in leads:
        who = f"@{lead.author_username}" if lead.author_username else "невідомий"
        where = lead.source.title or lead.source.identifier
        link = f"\n{lead.message_link}" if lead.message_link else ""
        blocks.append(
            f"🎯 «{lead.keyword.phrase}» у {where}\n"
            f"{lead.found_at:%d.%m %H:%M} — {who}\n"
            f"{lead.text_snippet[:200]}{link}"
        )
    await message.answer("\n\n".join(blocks))
