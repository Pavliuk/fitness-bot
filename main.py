"""Точка входу бота «Фітнес-тренер»."""
import asyncio
import json
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_config
from bot.database.engine import create_engine_and_sessionmaker, init_db
from bot.database.requests import bulk_add_exercises
from bot.handlers import nutrition, progress, reminders, start, workout
from bot.scheduler.reminders import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def _seed_exercises(session_maker) -> None:
    """Наповнює таблицю exercises стартовими даними з data/exercises.json."""
    data_path = Path(__file__).parent / "data" / "exercises.json"
    with open(data_path, encoding="utf-8") as f:
        exercises = json.load(f)
    async with session_maker() as session:
        await bulk_add_exercises(session, exercises)


async def main() -> None:
    config = load_config()

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    engine, session_maker = create_engine_and_sessionmaker(config.database_url)
    await init_db(engine)
    await _seed_exercises(session_maker)

    # session_maker пробрасываем в кожен хендлер через middleware-подібний контекст aiogram
    dp["session_maker"] = session_maker

    dp.include_router(start.router)
    dp.include_router(workout.router)
    dp.include_router(nutrition.router)
    dp.include_router(progress.router)
    dp.include_router(reminders.router)

    scheduler = setup_scheduler(bot, session_maker, config.timezone)
    scheduler.start()

    logger.info("Бот запускається...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинено.")
