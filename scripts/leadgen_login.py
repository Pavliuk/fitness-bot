"""Одноразовий інтерактивний вхід у Telegram user-акаунт для модуля лідогенерації.

Запускати ОДИН РАЗ локально (не в Docker-демоні, бо там немає інтерактивного
вводу), перед першим стартом бота з увімкненим TG_API_ID/TG_API_HASH:

    python scripts/leadgen_login.py

Скрипт запитає номер телефону, код підтвердження з Telegram (і, за потреби,
пароль двофакторної автентифікації) та збереже файл сесії за шляхом із
TG_SESSION_NAME (.env). Після цього main.py підключається до вже
авторизованої сесії без додаткових запитів.

Використовуйте акаунт, яким ви свідомо приєднуєтесь до потрібних публічних
груп/каналів для лідогенерації — не чужий і не тестовий "про всяк випадок".
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon import TelegramClient  # noqa: E402

from bot.config import load_config  # noqa: E402


async def main() -> None:
    config = load_config()
    if not config.tg_api_id or not config.tg_api_hash:
        raise SystemExit(
            "TG_API_ID / TG_API_HASH не задані у .env. "
            "Отримайте їх на https://my.telegram.org -> API development tools."
        )

    client = TelegramClient(config.tg_session_name, config.tg_api_id, config.tg_api_hash)
    await client.start()
    me = await client.get_me()
    print(f"Готово! Увійшли як {me.first_name} (@{me.username or me.id}).")
    print(f"Сесію збережено у {config.tg_session_name}.session — тепер можна запускати main.py")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
