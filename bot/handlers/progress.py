"""Хендлери розділу прогресу: статистика тренувань та зміна ваги."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.database.requests import (
    add_weight_log,
    get_completed_workouts_count,
    get_user_by_tg_id,
    get_weight_history,
)
from bot.states.registration import WeightLogging

router = Router(name="progress")


def progress_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📈 Статистика тренувань", callback_data="progress_workouts")],
            [InlineKeyboardButton(text="⚖️ Внести вагу", callback_data="progress_add_weight")],
            [InlineKeyboardButton(text="📉 Історія ваги", callback_data="progress_weight_history")],
        ]
    )


@router.message(F.text == "📊 Прогрес")
async def progress_menu(message: Message):
    await message.answer("Розділ прогресу:", reply_markup=progress_menu_kb())


@router.callback_query(F.data == "progress_workouts")
async def progress_workouts(callback: CallbackQuery, session_maker: async_sessionmaker):
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        count = await get_completed_workouts_count(session, user.id)
    await callback.message.answer(f"✅ Виконано вправ за весь час: {count}")
    await callback.answer()


@router.callback_query(F.data == "progress_add_weight")
async def start_add_weight(callback: CallbackQuery, state: FSMContext):
    await state.set_state(WeightLogging.waiting_weight)
    await callback.message.answer("Введи поточну вагу в кг:")
    await callback.answer()


@router.message(WeightLogging.waiting_weight)
async def save_weight(message: Message, state: FSMContext, session_maker: async_sessionmaker):
    try:
        weight = float(message.text.replace(",", "."))
        if not (30 <= weight <= 300):
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("Введи коректну вагу в кг, наприклад 71.5.")
        return

    async with session_maker() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        await add_weight_log(session, user.id, weight)

    await state.clear()
    await message.answer(f"Вагу {weight} кг збережено. ⚖️")


@router.callback_query(F.data == "progress_weight_history")
async def weight_history(callback: CallbackQuery, session_maker: async_sessionmaker):
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        history = await get_weight_history(session, user.id)

    if not history:
        await callback.message.answer("Записів про вагу ще немає.")
        await callback.answer()
        return

    lines = ["📉 Історія ваги:\n"]
    for log in history:
        lines.append(f"• {log.date}: {log.weight} кг")

    if len(history) >= 2:
        diff = history[-1].weight - history[0].weight
        sign = "+" if diff >= 0 else ""
        lines.append(f"\nЗміна з початку: {sign}{diff:.1f} кг")

    await callback.message.answer("\n".join(lines))
    await callback.answer()
