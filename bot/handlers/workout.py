"""Хендлери розділу тренувань: генерація плану, чекліст на день, лог підходів,
корегування плану (додавання/заміна/видалення вправ, вихідний/тренувальний день)
та позапланові тренування."""
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.database.requests import (
    add_exercise_to_day,
    deactivate_active_plans,
    delete_day_exercise,
    get_active_plan,
    get_day_exercise_by_id,
    get_day_for_date,
    get_exercise_by_id,
    get_exercises_by_group,
    get_logs_for_day,
    get_or_create_training_day,
    get_user_by_tg_id,
    log_adhoc_workout,
    save_set_log,
    set_day_rest_status,
    swap_day_exercise,
    toggle_workout_log,
    update_day_exercise_targets,
)
from bot.keyboards.workout import (
    checklist_kb,
    day_exercise_manage_kb,
    exercise_pick_kb,
    muscle_group_kb,
    plan_setup_kb,
)
from bot.services.workout_generator import generate_plan
from bot.states.registration import PlanEditing, WorkoutLogging

router = Router(name="workout")

WEEKDAY_NAMES = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
DIFFICULTY_LABELS = {"beginner": "🌱 Початківець", "intermediate": "⚙️ Середній", "advanced": "🏆 Просунутий"}


async def _require_registered_user(message_or_cb, session_maker):
    tg_id = message_or_cb.from_user.id
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, tg_id)
    return user


@router.message(F.text == "📅 План на тиждень")
async def show_plan_menu(message: Message, session_maker: async_sessionmaker):
    user = await _require_registered_user(message, session_maker)
    if not user or not user.is_registered:
        await message.answer("Спочатку пройди реєстрацію: /start")
        return

    async with session_maker() as session:
        plan = await get_active_plan(session, user.id)

    if plan is None:
        await message.answer(
            f"У тебе ще немає активного плану.\n"
            f"Ціль: {user.goal.value}, рівень: {user.level.value}.\n\n"
            f"На скільки тижнів згенерувати програму?",
            reply_markup=plan_setup_kb(),
        )
        return

    text_lines = [f"📅 Активний план ({plan.duration_weeks} тижн., тиждень старту {plan.start_date}):\n"]
    week1_days = [d for d in plan.days if d.week_number == 1]
    week1_days.sort(key=lambda d: d.day_of_week)
    for day in week1_days:
        ex_names = ", ".join(de.exercise.name for de in day.exercises)
        text_lines.append(f"• {WEEKDAY_NAMES[day.day_of_week]} — {day.focus}\n   {ex_names}")
    text_lines.append("\nПоказано тиждень 1 як приклад ротації. Дивись «🏋️ Сьогоднішнє тренування» для чеклиста дня.")
    await message.answer("\n".join(text_lines), reply_markup=plan_setup_kb())


@router.callback_query(F.data.startswith("plan_weeks:"))
async def generate_new_plan(callback: CallbackQuery, session_maker: async_sessionmaker):
    weeks = int(callback.data.split(":")[1])
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        if not user or not user.is_registered:
            await callback.answer("Спочатку пройди реєстрацію: /start", show_alert=True)
            return
        await deactivate_active_plans(session, user.id)
        await generate_plan(
            session,
            user_id=user.id,
            goal=user.goal,
            level=user.level,
            duration_weeks=weeks,
            start_date=date.today(),
        )
    await callback.message.edit_text(f"✅ Новий план на {weeks} тижн. згенеровано!")
    await callback.answer()


@router.callback_query(F.data == "plan_regen")
async def regenerate_plan(callback: CallbackQuery, session_maker: async_sessionmaker):
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        if not user:
            await callback.answer("Немає користувача", show_alert=True)
            return
        current = await get_active_plan(session, user.id)
        weeks = current.duration_weeks if current else 4
        await deactivate_active_plans(session, user.id)
        await generate_plan(
            session, user_id=user.id, goal=user.goal, level=user.level,
            duration_weeks=weeks, start_date=date.today(),
        )
    await callback.message.edit_text("🔁 План перегенеровано з новою ротацією вправ.")
    await callback.answer()


async def _render_today(session: AsyncSession, user_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    """Формує (текст, клавіатура) для сьогоднішнього тренування. None — якщо
    немає активного плану."""
    today = date.today()
    plan = await get_active_plan(session, user_id)
    if plan is None:
        return None

    day = await get_day_for_date(plan, today)
    is_rest = day is None or day.is_rest_day
    if is_rest:
        text = (
            "Сьогодні день відпочинку 😌 Не забувай про воду та розтяжку!\n\n"
            "Можеш зробити цей день тренувальним або записати позапланове тренування."
        )
        return text, checklist_kb([], {}, is_rest=True)

    logs = await get_logs_for_day(session, user_id, today)
    logs_by_exercise = {log.day_exercise_id: log for log in logs}

    text = f"🏋️ Тренування на сьогодні ({WEEKDAY_NAMES[today.weekday()]}) — {day.focus}\n\n"
    if day.exercises:
        for de in day.exercises:
            text += f"• {de.exercise.name}: {de.target_sets}×{de.target_reps}\n"
        text += "\nВідмічай виконані вправи нижче:"
    else:
        text += "Вправ поки немає — додай через кнопку нижче."
    return text, checklist_kb(day.exercises, logs_by_exercise, is_rest=False)


@router.message(F.text == "🏋️ Сьогоднішнє тренування")
async def show_today_workout(message: Message, session_maker: async_sessionmaker):
    user = await _require_registered_user(message, session_maker)
    if not user or not user.is_registered:
        await message.answer("Спочатку пройди реєстрацію: /start")
        return

    async with session_maker() as session:
        rendered = await _render_today(session, user.id)

    if rendered is None:
        await message.answer("У тебе ще немає активного плану. Натисни «📅 План на тиждень».")
        return
    text, kb = rendered
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("toggle:"))
async def toggle_exercise(callback: CallbackQuery, session_maker: async_sessionmaker):
    day_exercise_id = int(callback.data.split(":")[1])
    today = date.today()
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        await toggle_workout_log(session, user.id, day_exercise_id, today)
        plan = await get_active_plan(session, user.id)
        day = await get_day_for_date(plan, today)
        logs = await get_logs_for_day(session, user.id, today)
        logs_by_exercise = {log.day_exercise_id: log for log in logs}
    await callback.message.edit_reply_markup(
        reply_markup=checklist_kb(day.exercises, logs_by_exercise, is_rest=False)
    )
    await callback.answer("Оновлено ✅")


# ---------- Корегування плану: додати / замінити / видалити вправу, вихідний/тренувальний день ----------

@router.callback_query(F.data == "wex_add_start")
async def start_add_exercise(callback: CallbackQuery, state: FSMContext):
    await state.update_data(action="add")
    await callback.message.answer("Яка група м'язів?", reply_markup=muscle_group_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("de_manage:"))
async def manage_day_exercise(callback: CallbackQuery, session_maker: async_sessionmaker):
    day_exercise_id = int(callback.data.split(":")[1])
    async with session_maker() as session:
        day_exercise = await get_day_exercise_by_id(session, day_exercise_id)

    if day_exercise is None:
        await callback.answer("Вправу не знайдено", show_alert=True)
        return

    await callback.message.answer(
        f"✏️ {day_exercise.exercise.name}: {day_exercise.target_sets}×{day_exercise.target_reps}\nЩо зробити?",
        reply_markup=day_exercise_manage_kb(day_exercise_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("de_swap:"))
async def start_swap_exercise(callback: CallbackQuery, state: FSMContext):
    day_exercise_id = int(callback.data.split(":")[1])
    await state.update_data(action="swap", day_exercise_id=day_exercise_id)
    await callback.message.answer("Обери нову вправу — яка група м'язів?", reply_markup=muscle_group_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("de_edit:"))
async def start_edit_targets(callback: CallbackQuery, state: FSMContext):
    day_exercise_id = int(callback.data.split(":")[1])
    await state.update_data(action="edit", day_exercise_id=day_exercise_id)
    await state.set_state(PlanEditing.waiting_sets)
    await callback.message.answer("Скільки підходів? (число)")
    await callback.answer()


@router.callback_query(F.data.startswith("de_delete:"))
async def delete_exercise_from_day(callback: CallbackQuery, session_maker: async_sessionmaker):
    day_exercise_id = int(callback.data.split(":")[1])
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        await delete_day_exercise(session, day_exercise_id)
        rendered = await _render_today(session, user.id)

    await callback.message.answer("Вправу видалено з дня. 🗑")
    if rendered is not None:
        text, kb = rendered
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "day_make_rest")
async def make_day_rest(callback: CallbackQuery, session_maker: async_sessionmaker):
    today = date.today()
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        plan = await get_active_plan(session, user.id)
        day = await get_day_for_date(plan, today) if plan else None
        if day is not None:
            await set_day_rest_status(session, day.id, True)
        rendered = await _render_today(session, user.id)

    if rendered is not None:
        text, kb = rendered
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer("Позначено як вихідний")


@router.callback_query(F.data == "day_make_training")
async def make_day_training(callback: CallbackQuery, session_maker: async_sessionmaker):
    today = date.today()
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        plan = await get_active_plan(session, user.id)
        created = await get_or_create_training_day(session, plan, today) if plan else None
        rendered = await _render_today(session, user.id)

    if created is None:
        await callback.answer("План не покриває сьогоднішню дату — згенеруй новий план", show_alert=True)
        return
    if rendered is not None:
        text, kb = rendered
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer("Тепер сьогодні тренувальний день")


@router.callback_query(F.data == "adhoc_start")
async def start_adhoc_workout(callback: CallbackQuery, state: FSMContext):
    await state.update_data(action="adhoc")
    await callback.message.answer("Яка група м'язів?", reply_markup=muscle_group_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("wex_group:"))
async def pick_exercise_group(callback: CallbackQuery, session_maker: async_sessionmaker):
    group = callback.data.split(":", 1)[1]
    async with session_maker() as session:
        exercises = await get_exercises_by_group(session, group)

    if not exercises:
        await callback.answer("У цій групі поки немає вправ у базі", show_alert=True)
        return
    await callback.message.answer("Обери вправу:", reply_markup=exercise_pick_kb(exercises))
    await callback.answer()


@router.callback_query(F.data.startswith("wex_pick:"))
async def pick_exercise(callback: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker):
    exercise_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    action = data.get("action")

    if action == "swap":
        async with session_maker() as session:
            user = await get_user_by_tg_id(session, callback.from_user.id)
            await swap_day_exercise(session, data["day_exercise_id"], exercise_id)
            rendered = await _render_today(session, user.id)
        await state.clear()
        await callback.message.answer("Вправу замінено. ✅")
        if rendered is not None:
            text, kb = rendered
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()
        return

    await state.update_data(exercise_id=exercise_id)
    await state.set_state(PlanEditing.waiting_sets)
    await callback.message.answer("Скільки підходів? (число)")
    await callback.answer()


@router.message(PlanEditing.waiting_sets)
async def plan_edit_sets(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введи число підходів, наприклад 3.")
        return
    await state.update_data(sets=int(message.text))
    await state.set_state(PlanEditing.waiting_reps)
    await message.answer("Скільки повторень? (наприклад, 10-12)")


@router.message(PlanEditing.waiting_reps)
async def plan_edit_reps(message: Message, state: FSMContext, session_maker: async_sessionmaker):
    reps = (message.text or "").strip()
    if not reps:
        await message.answer("Введи кількість повторень, наприклад 10-12.")
        return
    await state.update_data(reps=reps)
    data = await state.get_data()
    action = data["action"]

    if action == "adhoc":
        await state.set_state(PlanEditing.waiting_weight)
        await message.answer("Яка робоча вага в кг? (0, якщо без ваги)")
        return

    async with session_maker() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        if action == "add":
            plan = await get_active_plan(session, user.id)
            day = await get_or_create_training_day(session, plan, date.today()) if plan else None
            if day is None:
                await state.clear()
                await message.answer("План не покриває сьогоднішню дату — згенеруй новий план.")
                return
            await add_exercise_to_day(session, day.id, data["exercise_id"], data["sets"], reps)
        else:  # "edit"
            await update_day_exercise_targets(session, data["day_exercise_id"], data["sets"], reps)
        rendered = await _render_today(session, user.id)

    await state.clear()
    await message.answer("Збережено. ✅")
    if rendered is not None:
        text, kb = rendered
        await message.answer(text, reply_markup=kb)


@router.message(PlanEditing.waiting_weight)
async def plan_adhoc_weight(message: Message, state: FSMContext, session_maker: async_sessionmaker):
    try:
        weight = float(message.text.replace(",", "."))
    except (ValueError, AttributeError):
        await message.answer("Введи вагу числом, наприклад 20 або 0.")
        return

    data = await state.get_data()
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        plan = await get_active_plan(session, user.id)
        if plan is None:
            await state.clear()
            await message.answer("У тебе більше немає активного плану — спочатку згенеруй новий.")
            return
        await log_adhoc_workout(
            session, user.id, plan.id, data["exercise_id"], data["sets"], data["reps"], weight
        )

    await state.clear()
    await message.answer(
        f"Позапланове тренування записано: {data['sets']} підходів × {data['reps']} повт. × {weight} кг. 💪"
    )


@router.callback_query(F.data.startswith("exercise_info:"))
async def show_exercise_info(callback: CallbackQuery, session_maker: async_sessionmaker):
    exercise_id = int(callback.data.split(":")[1])
    async with session_maker() as session:
        exercise = await get_exercise_by_id(session, exercise_id)

    if exercise is None:
        await callback.answer("Вправу не знайдено", show_alert=True)
        return

    difficulty_label = DIFFICULTY_LABELS.get(exercise.difficulty.value, exercise.difficulty.value)
    await callback.message.answer(
        f"ℹ️ <b>{exercise.name}</b> ({difficulty_label})\n\n{exercise.description}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("logset:"))
async def start_log_set(callback: CallbackQuery, state: FSMContext):
    day_exercise_id = int(callback.data.split(":")[1])
    await state.update_data(day_exercise_id=day_exercise_id)
    await state.set_state(WorkoutLogging.waiting_sets)
    await callback.message.answer("Скільки підходів виконано? (число)")
    await callback.answer()


@router.message(WorkoutLogging.waiting_sets)
async def log_sets(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введи число підходів, наприклад 3.")
        return
    await state.update_data(sets=int(message.text))
    await state.set_state(WorkoutLogging.waiting_reps)
    await message.answer("Скільки повторень у підході? (наприклад, 12 або 10-12)")


@router.message(WorkoutLogging.waiting_reps)
async def log_reps(message: Message, state: FSMContext):
    await state.update_data(reps=message.text)
    await state.set_state(WorkoutLogging.waiting_weight)
    await message.answer("Яка робоча вага в кг? (0, якщо без ваги)")


@router.message(WorkoutLogging.waiting_weight)
async def log_weight(message: Message, state: FSMContext, session_maker: async_sessionmaker):
    try:
        weight = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введи вагу числом, наприклад 20 або 0.")
        return

    data = await state.get_data()
    async with session_maker() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)
        await save_set_log(
            session,
            user_id=user.id,
            day_exercise_id=data["day_exercise_id"],
            target_date=date.today(),
            sets=data["sets"],
            reps=data["reps"],
            weight=weight,
        )
    await state.clear()
    await message.answer(
        f"Записано: {data['sets']} підходів × {data['reps']} повт. × {weight} кг. 💪"
    )
