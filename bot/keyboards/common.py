"""Головне меню та загальні клавіатури."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

MAIN_MENU_BUTTONS = [
    ["🏋️ Сьогоднішнє тренування", "📅 План на тиждень"],
    ["🍽 Харчування", "📊 Прогрес"],
    ["⚙️ Налаштування нагадувань"],
    ["🎬 Мотиваційне відео"],
]


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b) for b in row] for row in MAIN_MENU_BUTTONS],
        resize_keyboard=True,
    )
