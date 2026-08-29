"""Точка входу бота «Фітнес-тренер»."""
import asyncio
import base64
import json
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import load_config
from bot.database.engine import create_engine_and_sessionmaker, init_db
from bot.database.requests import bulk_add_exercises
from bot.handlers import misc, nutrition, progress, reminders, start, workout
from bot.leadgen import handlers as leadgen_handlers
from bot.leadgen.scheduler import setup_leadgen_scheduler
from bot.leadgen.telegram_monitor import LeadMonitor
from bot.scheduler.reminders import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def _seed_exercises(session_maker) -> None:
    """Наповнює таблицю exercises стартовими даними з assets/exercises.json."""
    data_path = Path(__file__).parent / "assets" / "exercises.json"
    with open(data_path, encoding="utf-8") as f:
        exercises = json.load(f)
    async with session_maker() as session:
        await bulk_add_exercises(session, exercises)


def _restore_session_from_env(tg_session_name: str, tg_session_b64: str | None) -> None:
    """Відновлює файл Telethon-сесії з TG_SESSION_B64, якщо він заданий.

    Потрібно для хостингів на кшталт Railway: volume нового сервісу завжди
    порожній, а Telethon-логін інтерактивний (запитує код із SMS), тому
    пройти його прямо в контейнері неможливо. Натомість сесію логінять
    локально (scripts/leadgen_login.py), а її вміст у вигляді base64-рядка
    просто вставляють як звичайну змінну середовища.
    """
    if not tg_session_b64:
        return
    session_path = Path(f"{tg_session_name}.session")
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_bytes(base64.b64decode(tg_session_b64))
    logger.info("Leadgen: сесію Telethon відновлено з TG_SESSION_B64 -> %s", session_path)


async def main() -> None:
    config = load_config()
    logger.info("Режим запуску: BOT_MODE=%s", config.bot_mode)

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    engine, session_maker = create_engine_and_sessionmaker(config.database_url)
    await init_db(engine)

    # session_maker пробрасываем в кожен хендлер через middleware-подібний контекст aiogram
    dp["session_maker"] = session_maker
    dp["admin_ids"] = config.admin_ids

    scheduler = AsyncIOScheduler(timezone=config.timezone)
    monitor: LeadMonitor | None = None

    if config.bot_mode == "fitness":
        if not config.anthropic_api_key:
            logger.warning(
                "Не задано ANTHROPIC_API_KEY — розпізнавання БЖУ за фото не працюватиме, "
                "решта фітнес-функцій запуститься як зазвичай."
            )
        await _seed_exercises(session_maker)
        dp.include_router(start.router)
        dp.include_router(workout.router)
        dp.include_router(nutrition.router)
        dp.include_router(progress.router)
        dp.include_router(reminders.router)
        dp.include_router(misc.router)
        setup_scheduler(scheduler, bot, session_maker, config.timezone)
    else:  # "leadgen"
        dp.include_router(leadgen_handlers.router)
        if config.tg_api_id and config.tg_api_hash and config.admin_ids:
            _restore_session_from_env(config.tg_session_name, config.tg_session_b64)
            monitor = LeadMonitor(config.tg_api_id, config.tg_api_hash, config.tg_session_name, session_maker)
            setup_leadgen_scheduler(scheduler, bot, session_maker, config.admin_ids, config.timezone)
        else:
            logger.warning(
                "Leadgen: не вистачає TG_API_ID/TG_API_HASH/ADMIN_IDS у .env — "
                "бот запуститься, але моніторинг груп не працюватиме."
            )

    scheduler.start()

    logger.info("Бот запускається...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)

        async def _notify_admins(text: str) -> None:
            for admin_id in config.admin_ids:
                try:
                    await bot.send_message(admin_id, text)
                except Exception:
                    logger.exception("Leadgen: не вдалося сповістити admin_id=%s", admin_id)

        if monitor is not None:
            try:
                await monitor.start(_notify_admins)
            except Exception:
                logger.exception(
                    "Leadgen: не вдалося запустити моніторинг груп — бот продовжить "
                    "працювати з адмінськими командами, але без пошуку лідів."
                )
                monitor = None

        if monitor is not None:
            await asyncio.gather(dp.start_polling(bot), monitor.run_until_disconnected())
        else:
            await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        if monitor is not None:
            await monitor.stop()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинено.")
