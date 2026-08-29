"""Хендлер налаштувань нагадувань: типи, час і «тихі години» (без сповіщень уночі)."""
from datetime import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.database.requests import get_reminder_settings, get_user_by_tg_id
from bot.states.registration import ReminderTimeInput

router = Router(name="reminders")

_TIME_FIELD_LABELS = {
    "workout_time": "час нагадування про тренування",
    "water_start": "початок вікна нагадувань про воду",
    "water_end": "кінець вікна нагадувань про воду",
    "breakfast_time": "час нагадування про сніданок",
    "lunch_time": "час нагадування про обід",
    "dinner_time": "час нагадування про вечерю",
    "sleep_time": "час нагадування лягати спати",
    "quiet_start": "початок тихих годин",
    "quiet_end": "кінець тихих годин",
}


def _t(value: time) -> str:
    return value.strftime("%H:%M")


def _settings_kb(settings) -> InlineKeyboardMarkup:
    def mark(flag: bool) -> str:
        return "✅" if flag else "❌"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{mark(settings.workout_enabled)} Тренування",
                callback_data="rem_toggle:workout",
            )],
            [InlineKeyboardButton(
                text=f"✏️ Час: {_t(settings.workout_time)}",
                callback_data="rem_edit_time:workout_time",
            )],

            [InlineKeyboardButton(
                text=f"{mark(settings.water_enabled)} Вода (кожні {settings.water_interval_min} хв)",
                callback_data="rem_toggle:water",
            )],
            [
                InlineKeyboardButton(text=f"✏️ З {_t(settings.water_start)}", callback_data="rem_edit_time:water_start"),
                InlineKeyboardButton(text=f"✏️ До {_t(settings.water_end)}", callback_data="rem_edit_time:water_end"),
            ],
            [InlineKeyboardButton(text="✏️ Змінити інтервал", callback_data="rem_edit_interval")],

            [InlineKeyboardButton(
                text=f"{mark(settings.meals_enabled)} Прийоми їжі",
                callback_data="rem_toggle:meals",
            )],
            [
                InlineKeyboardButton(text=f"✏️ Сніданок {_t(settings.breakfast_time)}", callback_data="rem_edit_time:breakfast_time"),
                InlineKeyboardButton(text=f"✏️ Обід {_t(settings.lunch_time)}", callback_data="rem_edit_time:lunch_time"),
            ],
            [InlineKeyboardButton(text=f"✏️ Вечеря {_t(settings.dinner_time)}", callback_data="rem_edit_time:dinner_time")],

            [InlineKeyboardButton(
                text=f"{mark(settings.sleep_enabled)} Нагадування про сон",
                callback_data="rem_toggle:sleep",
            )],
            [InlineKeyboardButton(text=f"✏️ Час: {_t(settings.sleep_time)}", callback_data="rem_edit_time:sleep_time")],

            [
                InlineKeyboardButton(text=f"🌙 Тиша з {_t(settings.quiet_start)}", callback_data="rem_edit_time:quiet_start"),
                InlineKeyboardButton(text=f"до {_t(settings.quiet_end)}", callback_data="rem_edit_time:quiet_end"),
            ],
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
        "Тут можна вмикати/вимикати типи нагадувань і налаштовувати їхній час.\n\n"
        "🌙 «Тихі години» — у цей проміжок жодні нагадування (крім самого "
        "«час спати») не надсилатимуться, щоб не турбувати вночі.",
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
        elif field == "sleep":
            settings.sleep_enabled = not settings.sleep_enabled
        session.add(settings)
        await session.commit()
        await session.refresh(settings)

    await callback.message.edit_reply_markup(reply_markup=_settings_kb(settings))
    await callback.answer("Оновлено")


def _parse_time(text: str | None) -> time | None:
    if not text:
        return None
    parts = text.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        return time(int(parts[0]), int(parts[1]))
    except ValueError:
        return None


@router.callback_query(F.data.startswith("rem_edit_time:"))
async def start_edit_time(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    label = _TIME_FIELD_LABELS.get(field, field)
    await state.set_state(ReminderTimeInput.waiting_time)
    await state.update_data(field=field)
    await callback.message.answer(f"Введи новий {label} у форматі ГГ:ХХ (наприклад, 07:30):")
    await callback.answer()


@router.message(ReminderTimeInput.waiting_time)
async def save_edited_time(message: Message, state: FSMContext, session_maker: async_sessionmaker):
    value = _parse_time(message.text)
    if value is None:
        await message.answer("Введи час у форматі ГГ:ХХ, наприклад 07:30.")
        return

    data = await state.get_data()
    field = data["field"]

    async with session_maker() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        settings = await get_reminder_settings(session, user.id)
        setattr(settings, field, value)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)

    await state.clear()
    await message.answer(
        f"Час оновлено: {_t(value)}. ✅", reply_markup=_settings_kb(settings)
    )


@router.callback_query(F.data == "rem_edit_interval")
async def start_edit_interval(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ReminderTimeInput.waiting_water_interval)
    await callback.message.answer("Введи інтервал нагадувань про воду в хвилинах (від 10 до 600, наприклад 90):")
    await callback.answer()


@router.message(ReminderTimeInput.waiting_water_interval)
async def save_water_interval(message: Message, state: FSMContext, session_maker: async_sessionmaker):
    if not message.text or not message.text.isdigit() or not (10 <= int(message.text) <= 600):
        await message.answer("Введи ціле число хвилин від 10 до 600, наприклад 90.")
        return
    minutes = int(message.text)

    async with session_maker() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        settings = await get_reminder_settings(session, user.id)
        settings.water_interval_min = minutes
        session.add(settings)
        await session.commit()
        await session.refresh(settings)

    await state.clear()
    await message.answer(f"Інтервал оновлено: кожні {minutes} хв. ✅", reply_markup=_settings_kb(settings))
