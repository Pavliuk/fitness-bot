"""Хендлери щоденника харчування (калорії/БЖУ)."""
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.database.requests import add_meal, get_meals_for_day, get_user_by_tg_id
from bot.services.nutrition_calc import calculate_daily_targets
from bot.states.registration import NutritionLogging

router = Router(name="nutrition")


def nutrition_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Додати прийом їжі", callback_data="meal_add")],
            [InlineKeyboardButton(text="📋 Сьогоднішній щоденник", callback_data="meal_today")],
            [InlineKeyboardButton(text="🎯 Моя денна норма", callback_data="meal_targets")],
        ]
    )


@router.message(F.text == "🍽 Харчування")
async def nutrition_menu(message: Message):
    await message.answer("Розділ харчування:", reply_markup=nutrition_menu_kb())


@router.callback_query(F.data == "meal_add")
async def start_add_meal(callback, state: FSMContext):
    await state.set_state(NutritionLogging.waiting_name)
    await callback.message.answer("Назва прийому їжі (наприклад, «Курка з рисом»):")
    await callback.answer()


@router.message(NutritionLogging.waiting_name)
async def meal_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(NutritionLogging.waiting_calories)
    await message.answer("Скільки калорій? (ккал, число)")


def _parse_float(text: str) -> float | None:
    try:
        return float(text.replace(",", "."))
    except (ValueError, AttributeError):
        return None


@router.message(NutritionLogging.waiting_calories)
async def meal_calories(message: Message, state: FSMContext):
    value = _parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введи число, наприклад 450.")
        return
    await state.update_data(calories=value)
    await state.set_state(NutritionLogging.waiting_protein)
    await message.answer("Скільки білків (г)?")


@router.message(NutritionLogging.waiting_protein)
async def meal_protein(message: Message, state: FSMContext):
    value = _parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введи число, наприклад 30.")
        return
    await state.update_data(protein=value)
    await state.set_state(NutritionLogging.waiting_fat)
    await message.answer("Скільки жирів (г)?")


@router.message(NutritionLogging.waiting_fat)
async def meal_fat(message: Message, state: FSMContext):
    value = _parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введи число, наприклад 15.")
        return
    await state.update_data(fat=value)
    await state.set_state(NutritionLogging.waiting_carbs)
    await message.answer("Скільки вуглеводів (г)?")


@router.message(NutritionLogging.waiting_carbs)
async def meal_carbs(message: Message, state: FSMContext, session_maker: async_sessionmaker):
    value = _parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введи число, наприклад 50.")
        return

    data = await state.get_data()
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        await add_meal(
            session,
            user_id=user.id,
            name=data["name"],
            calories=data["calories"],
            protein=data["protein"],
            fat=data["fat"],
            carbs=value,
        )
    await state.clear()
    await message.answer(
        f"Додано «{data['name']}»: {data['calories']} ккал "
        f"(Б {data['protein']} / Ж {data['fat']} / В {value}). ✅"
    )


@router.callback_query(F.data == "meal_today")
async def meal_today(callback, session_maker: async_sessionmaker):
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        meals = await get_meals_for_day(session, user.id, date.today())

    if not meals:
        await callback.message.answer("Сьогодні ще немає записів. Додай перший прийом їжі!")
        await callback.answer()
        return

    total_cal = sum(m.calories for m in meals)
    total_p = sum(m.protein for m in meals)
    total_f = sum(m.fat for m in meals)
    total_c = sum(m.carbs for m in meals)

    lines = [f"📋 Щоденник за {date.today()}:\n"]
    for m in meals:
        lines.append(f"• {m.name} — {m.calories:.0f} ккал (Б{m.protein:.0f}/Ж{m.fat:.0f}/В{m.carbs:.0f})")
    lines.append(f"\nВсього: {total_cal:.0f} ккал | Б {total_p:.0f} г / Ж {total_f:.0f} г / В {total_c:.0f} г")
    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data == "meal_targets")
async def meal_targets(callback, session_maker: async_sessionmaker):
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)

    if not user or not user.is_registered:
        await callback.message.answer("Спочатку пройди реєстрацію: /start")
        await callback.answer()
        return

    targets = calculate_daily_targets(user.gender, user.weight, user.height, user.age, user.goal)
    await callback.message.answer(
        "🎯 Твоя орієнтовна денна норма:\n\n"
        f"Базовий обмін (BMR): {targets['bmr']} ккал\n"
        f"Загальні витрати (TDEE): {targets['tdee']} ккал\n"
        f"Рекомендована калорійність: {targets['target_calories']} ккал\n\n"
        f"Білки: {targets['protein_g']} г\n"
        f"Жири: {targets['fat_g']} г\n"
        f"Вуглеводи: {targets['carbs_g']} г\n\n"
        "Це орієнтовний розрахунок за формулою Міффліна-Сан Жеора, "
        "не медична рекомендація."
    )
    await callback.answer()
