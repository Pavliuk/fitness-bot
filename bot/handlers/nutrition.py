"""Хендлери щоденника харчування (калорії/БЖУ) та персональної бази продуктів."""
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.database.requests import (
    add_meal,
    add_product,
    delete_product,
    get_meals_for_day,
    get_product_by_id,
    get_products_for_user,
    get_user_by_tg_id,
)
from bot.services.nutrition_calc import calculate_daily_targets
from bot.states.registration import MealFromProduct, NutritionLogging, ProductManagement

router = Router(name="nutrition")


def nutrition_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Додати прийом їжі", callback_data="meal_add")],
            [InlineKeyboardButton(text="📋 Сьогоднішній щоденник", callback_data="meal_today")],
            [InlineKeyboardButton(text="🎯 Моя денна норма", callback_data="meal_targets")],
            [InlineKeyboardButton(text="📦 Мої продукти", callback_data="products_menu")],
        ]
    )


@router.message(F.text == "🍽 Харчування")
async def nutrition_menu(message: Message):
    await message.answer("Розділ харчування:", reply_markup=nutrition_menu_kb())


def _add_meal_source_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Обрати зі своїх продуктів", callback_data="meal_from_products")],
            [InlineKeyboardButton(text="✍️ Ввести вручну", callback_data="meal_manual")],
        ]
    )


@router.callback_query(F.data == "meal_add")
async def start_add_meal(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await callback.message.answer(
        "Як додати прийом їжі?", reply_markup=_add_meal_source_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "meal_manual")
async def start_add_meal_manual(callback: CallbackQuery, state: FSMContext):
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


# ---------- Додавання прийому їжі з бази продуктів ----------

def _products_pick_kb(products) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=p.name, callback_data=f"product_pick:{p.id}")]
        for p in products
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "meal_from_products")
async def meal_from_products(callback: CallbackQuery, session_maker: async_sessionmaker):
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        products = await get_products_for_user(session, user.id)

    if not products:
        await callback.message.answer(
            "У тебе ще немає збережених продуктів. Додай їх у розділі «📦 Мої продукти»."
        )
        await callback.answer()
        return

    await callback.message.answer("Обери продукт:", reply_markup=_products_pick_kb(products))
    await callback.answer()


@router.callback_query(F.data.startswith("product_pick:"))
async def product_pick(callback: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker):
    product_id = int(callback.data.split(":")[1])
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        product = await get_product_by_id(session, user.id, product_id)

    if product is None:
        await callback.message.answer("Цей продукт більше не доступний.")
        await callback.answer()
        return

    await state.set_state(MealFromProduct.waiting_grams)
    await state.update_data(product_id=product.id)
    await callback.message.answer(f"Скільки грамів «{product.name}» ти з'їв(-ла)?")
    await callback.answer()


@router.message(MealFromProduct.waiting_grams)
async def meal_from_product_grams(message: Message, state: FSMContext, session_maker: async_sessionmaker):
    grams = _parse_float(message.text)
    if grams is None or grams <= 0:
        await message.answer("Введи кількість грамів числом, наприклад 150.")
        return

    data = await state.get_data()
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        product = await get_product_by_id(session, user.id, data["product_id"])
        if product is None:
            await state.clear()
            await message.answer("Цей продукт більше не доступний.")
            return

        factor = grams / 100
        meal = await add_meal(
            session,
            user_id=user.id,
            name=f"{product.name} ({grams:.0f} г)",
            calories=product.calories * factor,
            protein=product.protein * factor,
            fat=product.fat * factor,
            carbs=product.carbs * factor,
        )

    await state.clear()
    await message.answer(
        f"Додано «{meal.name}»: {meal.calories:.0f} ккал "
        f"(Б {meal.protein:.0f} / Ж {meal.fat:.0f} / В {meal.carbs:.0f}). ✅"
    )


# ---------- Управління персональною базою продуктів ----------

def _products_menu_kb(products) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="➕ Додати продукт", callback_data="product_add")]]
    for p in products:
        rows.append(
            [InlineKeyboardButton(text=f"🗑 {p.name}", callback_data=f"product_delete:{p.id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "products_menu")
async def products_menu(callback: CallbackQuery, session_maker: async_sessionmaker):
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        products = await get_products_for_user(session, user.id)

    if not products:
        text = "📦 Твоя база продуктів порожня.\n\nБЖУ та калорії вказуються на 100 г продукту."
    else:
        lines = ["📦 Твої продукти (на 100 г):\n"]
        for p in products:
            lines.append(
                f"• {p.name} — {p.calories:.0f} ккал (Б{p.protein:.0f}/Ж{p.fat:.0f}/В{p.carbs:.0f})"
            )
        lines.append("\nНатисни на 🗑, щоб видалити продукт.")
        text = "\n".join(lines)

    await callback.message.answer(text, reply_markup=_products_menu_kb(products))
    await callback.answer()


@router.callback_query(F.data.startswith("product_delete:"))
async def product_delete(callback: CallbackQuery, session_maker: async_sessionmaker):
    product_id = int(callback.data.split(":")[1])
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        removed = await delete_product(session, user.id, product_id)
        products = await get_products_for_user(session, user.id)

    await callback.answer("Видалено" if removed else "Продукт не знайдено")
    await callback.message.edit_text(
        "📦 Твої продукти (на 100 г):" if products else "📦 Твоя база продуктів порожня.",
        reply_markup=_products_menu_kb(products),
    )


@router.callback_query(F.data == "product_add")
async def start_add_product(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProductManagement.waiting_name)
    await callback.message.answer(
        "Назва продукту (наприклад, «Куряче філе»):"
    )
    await callback.answer()


@router.message(ProductManagement.waiting_name)
async def product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ProductManagement.waiting_calories)
    await message.answer("Скільки калорій на 100 г? (ккал, число)")


@router.message(ProductManagement.waiting_calories)
async def product_calories(message: Message, state: FSMContext):
    value = _parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введи число, наприклад 165.")
        return
    await state.update_data(calories=value)
    await state.set_state(ProductManagement.waiting_protein)
    await message.answer("Скільки білків на 100 г? (г)")


@router.message(ProductManagement.waiting_protein)
async def product_protein(message: Message, state: FSMContext):
    value = _parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введи число, наприклад 31.")
        return
    await state.update_data(protein=value)
    await state.set_state(ProductManagement.waiting_fat)
    await message.answer("Скільки жирів на 100 г? (г)")


@router.message(ProductManagement.waiting_fat)
async def product_fat(message: Message, state: FSMContext):
    value = _parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введи число, наприклад 3.6.")
        return
    await state.update_data(fat=value)
    await state.set_state(ProductManagement.waiting_carbs)
    await message.answer("Скільки вуглеводів на 100 г? (г)")


@router.message(ProductManagement.waiting_carbs)
async def product_carbs(message: Message, state: FSMContext, session_maker: async_sessionmaker):
    value = _parse_float(message.text)
    if value is None or value < 0:
        await message.answer("Введи число, наприклад 0.")
        return

    data = await state.get_data()
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        await add_product(
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
        f"Продукт «{data['name']}» додано до бази: {data['calories']} ккал "
        f"(Б {data['protein']} / Ж {data['fat']} / В {value}) на 100 г. ✅"
    )
