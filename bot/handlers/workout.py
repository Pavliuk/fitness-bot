"""Хендлери розділу тренувань: генерація плану, чекліст на день, лог підходів."""
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.database.requests import (
    deactivate_active_plans,
    get_active_plan,
    get_day_for_date,
    get_exercise_by_id,
    get_logs_for_day,
    get_user_by_tg_id,
    save_set_log,
    toggle_workout_log,
)
from bot.keyboards.workout import checklist_kb, plan_setup_kb
from bot.services.workout_generator import generate_plan
from bot.states.registration import WorkoutLogging

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


@router.message(F.text == "🏋️ Сьогоднішнє тренування")
async def show_today_workout(message: Message, session_maker: async_sessionmaker):
    user = await _require_registered_user(message, session_maker)
    if not user or not user.is_registered:
        await message.answer("Спочатку пройди реєстрацію: /start")
        return

    today = date.today()
    async with session_maker() as session:
        plan = await get_active_plan(session, user.id)
        if plan is None:
            await message.answer("У тебе ще немає активного плану. Натисни «📅 План на тиждень».")
            return
        day = await get_day_for_date(plan, today)
        if day is None or day.is_rest_day or not day.exercises:
            await message.answer("Сьогодні день відпочинку 😌 Не забувай про воду та розтяжку!")
            return
        logs = await get_logs_for_day(session, user.id, today)
        logs_by_exercise = {log.day_exercise_id: log for log in logs}

        text = f"🏋️ Тренування на сьогодні ({WEEKDAY_NAMES[today.weekday()]}) — {day.focus}\n\n"
        for de in day.exercises:
            text += f"• {de.exercise.name}: {de.target_sets}×{de.target_reps}\n"
        text += "\nВідмічай виконані вправи нижче:"
        await message.answer(text, reply_markup=checklist_kb(day.exercises, logs_by_exercise))


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
    await callback.message.edit_reply_markup(reply_markup=checklist_kb(day.exercises, logs_by_exercise))
    await callback.answer("Оновлено ✅")


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
