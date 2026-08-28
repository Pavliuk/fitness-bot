"""Завантаження конфігурації бота зі змінних середовища (.env)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    database_url: str
    timezone: str


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не знайдено. Скопіюйте .env.example у .env "
            "та вкажіть токен, отриманий у @BotFather."
        )
    return Config(
        bot_token=token,
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/fitness.db"),
        timezone=os.getenv("TIMEZONE", "Europe/Kyiv"),
    )
