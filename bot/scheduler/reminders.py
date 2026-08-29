"""
Планувальник нагадувань на базі APScheduler.

Підхід: одна фонова задача раз на хвилину («тік») перевіряє поточний час
і надсилає нагадування тим користувачам, чий час налаштувань співпав.
Це простіше й надійніше для SQLite/малих проєктів, ніж створювати
окрему job на кожного користувача (яку довелось би перестворювати
при кожній зміні налаштувань).
"""
import logging
from datetime import datetime, time, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.database.models import Meal
from bot.database.requests import get_all_users_with_reminders

logger = logging.getLogger(__name__)


def _time_matches(now: time, target: time) -> bool:
    return now.hour == target.hour and now.minute == target.minute


def _in_quiet_hours(now: time, start: time, end: time) -> bool:
    """Тихі години можуть переходити через північ (напр. 23:00–07:00)."""
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


async def _tick(bot: Bot, session_maker: async_sessionmaker) -> None:
    now = datetime.now().time().replace(second=0, microsecond=0)

    async with session_maker() as session:
        users = await get_all_users_with_reminders(session)

    for user in users:
        settings = user.reminder_settings
        if settings is None:
            continue

        # Нагадування про сон — єдине, що навмисно може прозвучати на межі тихих
        # годин (це і є повідомлення "час лягати спати"), тому воно не фільтрується.
        quiet = _in_quiet_hours(now, settings.quiet_start, settings.quiet_end)

        try:
            if settings.sleep_enabled and _time_matches(now, settings.sleep_time):
                await bot.send_message(user.tg_id, "😴 Час лягати спати! Якісний сон — важлива частина прогресу.")

            if quiet:
                continue

            if settings.workout_enabled and _time_matches(now, settings.workout_time):
                await bot.send_message(
                    user.tg_id,
                    "🏋️ Час тренування! Відкрий «Сьогоднішнє тренування» в меню.",
                )

            if settings.meals_enabled:
                if _time_matches(now, settings.breakfast_time):
                    await bot.send_message(user.tg_id, "🍳 Час сніданку! Не забудь занести його в щоденник.")
                elif _time_matches(now, settings.lunch_time):
                    await bot.send_message(user.tg_id, "🍲 Час обіду! Занеси прийом їжі в щоденник.")
                elif _time_matches(now, settings.dinner_time):
                    await bot.send_message(user.tg_id, "🍽 Час вечері! Занеси прийом їжі в щоденник.")

            if settings.water_enabled and settings.water_start <= now <= settings.water_end:
                # Нагадування про воду кожні N хвилин від часу старту вікна
                start_minutes = settings.water_start.hour * 60 + settings.water_start.minute
                now_minutes = now.hour * 60 + now.minute
                if (now_minutes - start_minutes) % settings.water_interval_min == 0:
                    await bot.send_message(user.tg_id, "💧 Час випити склянку води!")
        except Exception:
            # Найчастіша причина — користувач заблокував бота. Не валимо весь тік.
            logger.exception("Не вдалося надіслати нагадування user_id=%s", user.tg_id)


def setup_scheduler(
    scheduler: AsyncIOScheduler, bot: Bot, session_maker: async_sessionmaker, timezone: str
) -> None:
    scheduler.add_job(
        _tick,
        trigger=CronTrigger(minute="*", timezone=timezone),
        args=[bot, session_maker],
        id="reminders_tick",
        replace_existing=True,
    )
