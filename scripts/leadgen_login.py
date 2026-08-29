"""Одноразовий інтерактивний вхід у Telegram user-акаунт для модуля лідогенерації.

Запускати ОДИН РАЗ локально (не в Docker-демоні, бо там немає інтерактивного
вводу), перед першим стартом бота з увімкненим TG_API_ID/TG_API_HASH:

    python scripts/leadgen_login.py

Скрипт запитає номер телефону, код підтвердження з Telegram (і, за потреби,
пароль двофакторної автентифікації), збереже файл сесії за шляхом із
TG_SESSION_NAME (.env) і виведе його вміст у вигляді base64-рядка.

Для запуску на хостингу (Railway тощо), де контейнер неінтерактивний і не
може пройти цей логін сам, скопіюйте виведений рядок у змінну середовища
TG_SESSION_B64 сервісу з лідогенерацією — main.py розпакує його у файл
сесії автоматично при старті. Для локального запуску нічого копіювати не
треба — main.py й так знайде файл сесії поруч.

Використовуйте акаунт, яким ви свідомо приєднуєтесь до потрібних публічних
груп/каналів для лідогенерації — не чужий і не тестовий "про всяк випадок".
"""
import asyncio
import base64
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
    await client.disconnect()

    session_path = Path(f"{config.tg_session_name}.session")
    b64 = base64.b64encode(session_path.read_bytes()).decode()
    print(f"\nСесію збережено локально у {session_path}.")
    print("\nДля деплою на хостинг скопіюйте рядок нижче цілком у змінну")
    print("середовища TG_SESSION_B64 сервісу з BOT_MODE=leadgen:\n")
    print(b64)


if __name__ == "__main__":
    asyncio.run(main())
