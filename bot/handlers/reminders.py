"""Хендлер налаштувань нагадувань (увімкнути/вимкнути типи нагадувань)."""
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.database.requests import get_reminder_settings, get_user_by_tg_id

router = Router(name="reminders")


def _settings_kb(settings) -> InlineKeyboardMarkup:
    def mark(flag: bool) -> str:
        return "✅" if flag else "❌"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{mark(settings.workout_enabled)} Нагадування про тренування ({settings.workout_time})",
                callback_data="rem_toggle:workout",
            )],
            [InlineKeyboardButton(
                text=f"{mark(settings.water_enabled)} Нагадування про воду (кожні {settings.water_interval_min} хв)",
                callback_data="rem_toggle:water",
            )],
            [InlineKeyboardButton(
                text=f"{mark(settings.meals_enabled)} Нагадування про прийоми їжі",
                callback_data="rem_toggle:meals",
            )],
        ]
    )


@router.message(F.text == "⚙️ Налаштування нагадувань")
async def reminder_settings_menu(message: Message, session_maker: async_sessionmaker):
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        if not user:
            await message.answer("Спочатку пройди реєстрацію: /start")
            return
        settings = await get_reminder_settings(session, user.id)

    await message.answer(
        "Тут можна вмикати/вимикати типи нагадувань.\n"
        "Час нагадувань поки що змінюється у налаштуваннях за замовчуванням "
        "(див. модель ReminderSettings) — легко розширити окремою анкетою.",
        reply_markup=_settings_kb(settings),
    )


@router.callback_query(F.data.startswith("rem_toggle:"))
async def toggle_reminder(callback: CallbackQuery, session_maker: async_sessionmaker):
    field = callback.data.split(":")[1]
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        settings = await get_reminder_settings(session, user.id)
        if field == "workout":
            settings.workout_enabled = not settings.workout_enabled
        elif field == "water":
            settings.water_enabled = not settings.water_enabled
        elif field == "meals":
            settings.meals_enabled = not settings.meals_enabled
        session.add(settings)
        await session.commit()
        await session.refresh(settings)

    await callback.message.edit_reply_markup(reply_markup=_settings_kb(settings))
    await callback.answer("Оновлено")
