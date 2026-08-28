"""Команда /start та FSM-анкета реєстрації користувача."""
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.database.models import Gender, Goal, Level
from bot.database.requests import get_or_create_user, save_registration
from bot.keyboards.common import main_menu_kb
from bot.keyboards.registration import gender_kb, goal_kb, level_kb
from bot.states.registration import Registration

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session_maker: async_sessionmaker):
    async with session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.username)

    if user.is_registered:
        await message.answer(
            "З поверненням! 👋 Обери дію в меню нижче.",
            reply_markup=main_menu_kb(),
        )
        return

    await state.set_state(Registration.gender)
    await message.answer(
        "Привіт! Я твій фітнес-тренер 🏋️\n\n"
        "Спершу пройдемо коротку анкету, щоб підібрати програму саме під тебе.\n\n"
        "Обери свою стать:",
        reply_markup=gender_kb(),
    )


@router.callback_query(Registration.gender, F.data.startswith("gender:"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender_value = callback.data.split(":")[1]
    await state.update_data(gender=gender_value)
    await state.set_state(Registration.age)
    await callback.message.edit_text(f"Стать: {gender_value}. ✅")
    await callback.message.answer("Скільки тобі повних років?")
    await callback.answer()


@router.message(Registration.age)
async def process_age(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit() or not (10 <= int(message.text) <= 100):
        await message.answer("Введи вік числом від 10 до 100, будь ласка.")
        return
    await state.update_data(age=int(message.text))
    await state.set_state(Registration.weight)
    await message.answer("Яка твоя вага в кг? (наприклад, 72.5)")


@router.message(Registration.weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
        if not (30 <= weight <= 300):
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("Введи вагу числом у кг (наприклад, 72.5).")
        return
    await state.update_data(weight=weight)
    await state.set_state(Registration.height)
    await message.answer("Який твій зріст у см? (наприклад, 175)")


@router.message(Registration.height)
async def process_height(message: Message, state: FSMContext):
    try:
        height = float(message.text.replace(",", "."))
        if not (100 <= height <= 250):
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("Введи зріст числом у см (наприклад, 175).")
        return
    await state.update_data(height=height)
    await state.set_state(Registration.goal)
    await message.answer("Яка твоя головна ціль?", reply_markup=goal_kb())


@router.callback_query(Registration.goal, F.data.startswith("goal:"))
async def process_goal(callback: CallbackQuery, state: FSMContext):
    goal_value = callback.data.split(":")[1]
    await state.update_data(goal=goal_value)
    await state.set_state(Registration.level)
    await callback.message.edit_text("Ціль збережено. ✅")
    await callback.message.answer("Який у тебе рівень підготовки?", reply_markup=level_kb())
    await callback.answer()


@router.callback_query(Registration.level, F.data.startswith("level:"))
async def process_level(
    callback: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker
):
    level_value = callback.data.split(":")[1]
    data = await state.update_data(level=level_value)

    async with session_maker() as session:
        user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
        await save_registration(
            session,
            user,
            gender=Gender(data["gender"]),
            age=data["age"],
            weight=data["weight"],
            height=data["height"],
            goal=Goal(data["goal"]),
            level=Level(data["level"]),
        )

    await state.clear()
    await callback.message.edit_text("Рівень збережено. ✅")
    await callback.message.answer(
        "Анкету заповнено! 🎉\n\n"
        "Тепер натисни «📅 План на тиждень», щоб згенерувати першу програму тренувань.",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()
