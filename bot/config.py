"""Завантаження конфігурації бота зі змінних середовища (.env)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


VALID_BOT_MODES = ("fitness", "leadgen")


@dataclass
class Config:
    bot_token: str
    database_url: str
    timezone: str
    bot_mode: str  # "fitness" | "leadgen" — які роутери/фонові задачі вмикати
    admin_ids: list[int]
    tg_api_id: int | None
    tg_api_hash: str | None
    tg_session_name: str
    tg_session_b64: str | None
    anthropic_api_key: str | None


def _parse_admin_ids(raw: str) -> list[int]:
    ids = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            ids.append(int(chunk))
    return ids


def load_config() -> Config:
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не знайдено. Скопіюйте .env.example у .env "
            "та вкажіть токен, отриманий у @BotFather."
        )

    bot_mode = (os.getenv("BOT_MODE") or "fitness").strip().lower()
    if bot_mode not in VALID_BOT_MODES:
        raise RuntimeError(
            f"BOT_MODE={bot_mode!r} невідомий. Дозволені значення: {', '.join(VALID_BOT_MODES)}."
        )

    tg_api_id_raw = (os.getenv("TG_API_ID") or "").strip()

    return Config(
        bot_token=token,
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/fitness.db").strip(),
        timezone=os.getenv("TIMEZONE", "Europe/Kyiv").strip(),
        bot_mode=bot_mode,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        tg_api_id=int(tg_api_id_raw) if tg_api_id_raw.isdigit() else None,
        tg_api_hash=(os.getenv("TG_API_HASH") or "").strip() or None,
        tg_session_name=(os.getenv("TG_SESSION_NAME") or "data/leadgen_session").strip(),
        tg_session_b64=(os.getenv("TG_SESSION_B64") or "").strip() or None,
        anthropic_api_key=(os.getenv("ANTHROPIC_API_KEY") or "").strip() or None,
    )
