"""Ініціалізація асинхронного підключення до БД."""
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.database.models import Base

# Нові колонки, додані до вже існуючих таблиць після першого релізу.
# create_all() створює нові таблиці, але не оновлює вже наявні — тому колонки,
# додані пізніше до моделі, доводиться підвантажувати вручну (без повноцінного Alembic).
_NEW_COLUMNS: dict[str, dict[str, str]] = {
    "reminder_settings": {
        "sleep_enabled": "BOOLEAN DEFAULT TRUE",
        "sleep_time": "TIME DEFAULT '22:30:00'",
        "quiet_start": "TIME DEFAULT '23:00:00'",
        "quiet_end": "TIME DEFAULT '07:00:00'",
    },
    "users": {
        "acquisition_source": "VARCHAR(64)",
    },
}


def create_engine_and_sessionmaker(database_url: str):
    engine = create_async_engine(database_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, session_maker


def _add_missing_columns(sync_conn) -> None:
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())

    for table_name, columns in _NEW_COLUMNS.items():
        if table_name not in existing_tables:
            continue  # щойно створена create_all() — уже містить усі колонки
        existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
        for column_name, ddl_type in columns.items():
            if column_name not in existing_columns:
                sync_conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type}"))


async def init_db(engine) -> None:
    """Створює таблиці, якщо їх ще немає, і підвантажує нові колонки в наявні (для старту без Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
