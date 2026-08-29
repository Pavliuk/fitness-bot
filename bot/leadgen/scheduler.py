"""Щоденний дайджест лідів адміністраторам бота."""
import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.leadgen.db import get_leads_last_24h

logger = logging.getLogger(__name__)


async def _send_daily_digest(bot: Bot, session_maker: async_sessionmaker, admin_ids: list[int]) -> None:
    if not admin_ids:
        return
    async with session_maker() as session:
        leads = await get_leads_last_24h(session)

    if leads:
        text = f"📊 Дайджест лідів за добу: знайдено {len(leads)}.\nОстанні — командою /leads"
    else:
        text = "📊 Дайджест лідів за добу: нових збігів не знайдено."

    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.exception("Leadgen: не вдалося надіслати дайджест admin_id=%s", admin_id)


def setup_leadgen_scheduler(
    scheduler: AsyncIOScheduler, bot: Bot, session_maker: async_sessionmaker, admin_ids: list[int], timezone: str
) -> None:
    scheduler.add_job(
        _send_daily_digest,
        trigger=CronTrigger(hour=9, minute=0, timezone=timezone),
        args=[bot, session_maker, admin_ids],
        id="leadgen_daily_digest",
        replace_existing=True,
    )
