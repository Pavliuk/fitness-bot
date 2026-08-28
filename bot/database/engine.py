"""Ініціалізація асинхронного підключення до БД."""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.database.models import Base


def create_engine_and_sessionmaker(database_url: str):
    engine = create_async_engine(database_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, session_maker


async def init_db(engine) -> None:
    """Створює таблиці, якщо їх ще немає (для старту без Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
