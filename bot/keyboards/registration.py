"""Клавіатури для анкети реєстрації."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def gender_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨 Чоловіча", callback_data="gender:male"),
                InlineKeyboardButton(text="👩 Жіноча", callback_data="gender:female"),
            ]
        ]
    )


def goal_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔥 Схуднення", callback_data="goal:weight_loss")],
            [InlineKeyboardButton(text="💪 Набір маси", callback_data="goal:muscle_gain")],
            [InlineKeyboardButton(text="🏃 Витривалість", callback_data="goal:endurance")],
        ]
    )


def level_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌱 Початківець", callback_data="level:beginner")],
            [InlineKeyboardButton(text="⚙️ Середній", callback_data="level:intermediate")],
            [InlineKeyboardButton(text="🏆 Просунутий", callback_data="level:advanced")],
        ]
    )
