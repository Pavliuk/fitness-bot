"""Допоміжні функції доступу до БД (простий шар "репозиторію")."""
from datetime import date

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import (
    Exercise,
    Goal,
    Level,
    Meal,
    Product,
    ReminderSettings,
    User,
    WeightLog,
    WorkoutDay,
    WorkoutDayExercise,
    WorkoutLog,
    WorkoutPlan,
)


# ---------- Користувачі ----------

async def get_or_create_user(
    session: AsyncSession, tg_id: int, username: str | None, source: str | None = None
) -> User:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(tg_id=tg_id, username=username, acquisition_source=source)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_user_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    return result.scalar_one_or_none()


async def get_acquisition_stats(session: AsyncSession) -> list[tuple[str, int, int]]:
    """Кількість користувачів і завершених реєстрацій по кожному джерелу трафіку."""
    result = await session.execute(
        select(
            func.coalesce(User.acquisition_source, "(без джерела)"),
            func.count(User.id),
            func.sum(cast(User.is_registered, Integer)),
        ).group_by(User.acquisition_source)
    )
    return [(source, total, registered or 0) for source, total, registered in result.all()]


async def save_registration(
    session: AsyncSession,
    user: User,
    gender,
    age: int,
    weight: float,
    height: float,
    goal,
    level,
) -> None:
    user.gender = gender
    user.age = age
    user.weight = weight
    user.height = height
    user.goal = goal
    user.level = level
    user.is_registered = True
    session.add(user)
    # Заводимо налаштування нагадувань за замовчуванням, якщо їх ще немає
    result = await session.execute(
        select(ReminderSettings).where(ReminderSettings.user_id == user.id)
    )
    if result.scalar_one_or_none() is None:
        session.add(ReminderSettings(user_id=user.id))
    # Перший запис ваги для графіка прогресу
    session.add(WeightLog(user_id=user.id, weight=weight, date=date.today()))
    await session.commit()


# ---------- Вправи ----------

async def get_exercises_by_group(session: AsyncSession, muscle_group) -> list[Exercise]:
    result = await session.execute(
        select(Exercise).where(Exercise.muscle_group == muscle_group)
    )
    return list(result.scalars().all())


async def get_all_exercises(session: AsyncSession) -> list[Exercise]:
    result = await session.execute(select(Exercise))
    return list(result.scalars().all())


async def get_exercise_by_id(session: AsyncSession, exercise_id: int) -> Exercise | None:
    return await session.get(Exercise, exercise_id)


async def bulk_add_exercises(session: AsyncSession, exercises: list[dict]) -> None:
    """Синхронізує таблицю exercises з assets/exercises.json: додає нові вправи
    (за назвою) та оновлює опис/медіа/складність уже існуючих — щоб уточнення
    техніки виконання підхоплювались і на вже задеплоєній базі, а не лише при
    першому запуску."""
    result = await session.execute(select(Exercise))
    existing_by_name = {e.name: e for e in result.scalars().all()}

    for item in exercises:
        existing = existing_by_name.get(item["name"])
        if existing is not None:
            existing.description = item.get("description", existing.description)
            existing.muscle_group = item["muscle_group"]
            existing.media_url = item.get("media_url")
            existing.difficulty = item.get("difficulty", existing.difficulty)
            session.add(existing)
        else:
            session.add(
                Exercise(
                    name=item["name"],
                    description=item.get("description", ""),
                    muscle_group=item["muscle_group"],
                    media_url=item.get("media_url"),
                    difficulty=item.get("difficulty", "beginner"),
                )
            )
    await session.commit()


# ---------- Плани тренувань ----------

async def deactivate_active_plans(session: AsyncSession, user_id: int) -> None:
    result = await session.execute(
        select(WorkoutPlan).where(WorkoutPlan.user_id == user_id, WorkoutPlan.is_active.is_(True))
    )
    for plan in result.scalars().all():
        plan.is_active = False
        session.add(plan)
    await session.commit()


async def get_active_plan(session: AsyncSession, user_id: int) -> WorkoutPlan | None:
    result = await session.execute(
        select(WorkoutPlan)
        .where(WorkoutPlan.user_id == user_id, WorkoutPlan.is_active.is_(True))
        .options(
            selectinload(WorkoutPlan.days)
            .selectinload(WorkoutDay.exercises)
            .selectinload(WorkoutDayExercise.exercise)
        )
        .order_by(WorkoutPlan.created_at.desc())
    )
    return result.scalars().first()


async def get_day_for_date(plan: WorkoutPlan, target_date: date) -> WorkoutDay | None:
    """Обчислює, який WorkoutDay плану відповідає календарній даті."""
    delta_days = (target_date - plan.start_date).days
    if delta_days < 0:
        return None
    week_number = delta_days // 7 + 1
    day_of_week = target_date.weekday()  # 0=Пн
    if week_number > plan.duration_weeks:
        return None
    for day in plan.days:
        if day.week_number == week_number and day.day_of_week == day_of_week:
            return day
    return None


async def get_or_create_training_day(
    session: AsyncSession, plan: WorkoutPlan, target_date: date
) -> WorkoutDay | None:
    """Повертає WorkoutDay для дати в межах плану, роблячи його тренувальним:
    якщо дня ще немає (шаблонний вихідний) — створює порожній тренувальний день,
    якщо є, але позначений як вихідний — знімає цю позначку. Повертає None, якщо
    дата виходить за межі тривалості плану (до старту або після його завершення)."""
    delta_days = (target_date - plan.start_date).days
    if delta_days < 0:
        return None
    week_number = delta_days // 7 + 1
    if week_number > plan.duration_weeks:
        return None

    day = await get_day_for_date(plan, target_date)
    if day is not None:
        if day.is_rest_day:
            day.is_rest_day = False
            session.add(day)
            await session.commit()
            await session.refresh(day)
        return day

    day = WorkoutDay(
        plan_id=plan.id,
        week_number=week_number,
        day_of_week=target_date.weekday(),
        focus="Додано вручну",
        is_rest_day=False,
    )
    session.add(day)
    await session.commit()
    return day


async def set_day_rest_status(session: AsyncSession, day_id: int, is_rest: bool) -> None:
    day = await session.get(WorkoutDay, day_id)
    if day is not None:
        day.is_rest_day = is_rest
        session.add(day)
        await session.commit()


# ---------- Вправи в межах тренувального дня ----------

async def get_day_exercise_by_id(session: AsyncSession, day_exercise_id: int) -> WorkoutDayExercise | None:
    result = await session.execute(
        select(WorkoutDayExercise)
        .where(WorkoutDayExercise.id == day_exercise_id)
        .options(selectinload(WorkoutDayExercise.exercise))
    )
    return result.scalar_one_or_none()


async def add_exercise_to_day(
    session: AsyncSession, day_id: int, exercise_id: int, target_sets: int, target_reps: str
) -> WorkoutDayExercise:
    result = await session.execute(
        select(WorkoutDayExercise.order)
        .where(WorkoutDayExercise.day_id == day_id)
        .order_by(WorkoutDayExercise.order.desc())
        .limit(1)
    )
    last_order = result.scalar_one_or_none()
    day_exercise = WorkoutDayExercise(
        day_id=day_id,
        exercise_id=exercise_id,
        order=(last_order + 1) if last_order is not None else 0,
        target_sets=target_sets,
        target_reps=target_reps,
    )
    session.add(day_exercise)
    await session.commit()
    return day_exercise


async def update_day_exercise_targets(
    session: AsyncSession, day_exercise_id: int, target_sets: int, target_reps: str
) -> None:
    day_exercise = await session.get(WorkoutDayExercise, day_exercise_id)
    if day_exercise is not None:
        day_exercise.target_sets = target_sets
        day_exercise.target_reps = target_reps
        session.add(day_exercise)
        await session.commit()


async def swap_day_exercise(session: AsyncSession, day_exercise_id: int, new_exercise_id: int) -> None:
    day_exercise = await session.get(WorkoutDayExercise, day_exercise_id)
    if day_exercise is not None:
        day_exercise.exercise_id = new_exercise_id
        session.add(day_exercise)
        await session.commit()


async def delete_day_exercise(session: AsyncSession, day_exercise_id: int) -> None:
    day_exercise = await session.get(WorkoutDayExercise, day_exercise_id)
    if day_exercise is not None:
        await session.delete(day_exercise)
        await session.commit()


# ---------- Позапланові тренування ----------

# Сентинельні значення (не збігаються з жодною реальною календарною датою, де
# week_number завжди >= 1, а day_of_week — 0..6), щоб зберігати позапланові
# логи через ту саму схему WorkoutDay/WorkoutDayExercise без міграції БД.
_ADHOC_WEEK_NUMBER = 0
_ADHOC_DAY_OF_WEEK = -1


async def _get_or_create_adhoc_day(session: AsyncSession, plan_id: int) -> WorkoutDay:
    result = await session.execute(
        select(WorkoutDay).where(
            WorkoutDay.plan_id == plan_id,
            WorkoutDay.week_number == _ADHOC_WEEK_NUMBER,
            WorkoutDay.day_of_week == _ADHOC_DAY_OF_WEEK,
        )
    )
    day = result.scalar_one_or_none()
    if day is not None:
        return day
    day = WorkoutDay(
        plan_id=plan_id,
        week_number=_ADHOC_WEEK_NUMBER,
        day_of_week=_ADHOC_DAY_OF_WEEK,
        focus="Позапланові тренування",
        is_rest_day=False,
    )
    session.add(day)
    await session.commit()
    return day


async def _get_or_create_adhoc_day_exercise(
    session: AsyncSession, day_id: int, exercise_id: int
) -> WorkoutDayExercise:
    result = await session.execute(
        select(WorkoutDayExercise).where(
            WorkoutDayExercise.day_id == day_id, WorkoutDayExercise.exercise_id == exercise_id
        )
    )
    day_exercise = result.scalar_one_or_none()
    if day_exercise is not None:
        return day_exercise
    day_exercise = WorkoutDayExercise(day_id=day_id, exercise_id=exercise_id, order=0)
    session.add(day_exercise)
    await session.commit()
    return day_exercise


async def log_adhoc_workout(
    session: AsyncSession,
    user_id: int,
    plan_id: int,
    exercise_id: int,
    sets: int,
    reps: str,
    weight: float | None,
) -> WorkoutLog:
    """Записує позапланове тренування (вправу, якої немає в сьогоднішньому
    плані) як завершений лог — без прив'язки до конкретного дня розкладу."""
    day = await _get_or_create_adhoc_day(session, plan_id)
    day_exercise = await _get_or_create_adhoc_day_exercise(session, day.id, exercise_id)
    log = WorkoutLog(
        user_id=user_id,
        day_exercise_id=day_exercise.id,
        date=date.today(),
        completed=True,
        actual_sets=sets,
        actual_reps=reps,
        actual_weight=weight,
    )
    session.add(log)
    await session.commit()
    return log


# ---------- Лог виконання тренувань ----------

async def toggle_workout_log(
    session: AsyncSession, user_id: int, day_exercise_id: int, target_date: date
) -> WorkoutLog:
    result = await session.execute(
        select(WorkoutLog).where(
            WorkoutLog.user_id == user_id,
            WorkoutLog.day_exercise_id == day_exercise_id,
            WorkoutLog.date == target_date,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        log = WorkoutLog(
            user_id=user_id,
            day_exercise_id=day_exercise_id,
            date=target_date,
            completed=True,
        )
    else:
        log.completed = not log.completed
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def save_set_log(
    session: AsyncSession,
    user_id: int,
    day_exercise_id: int,
    target_date: date,
    sets: int,
    reps: str,
    weight: float | None,
) -> WorkoutLog:
    result = await session.execute(
        select(WorkoutLog).where(
            WorkoutLog.user_id == user_id,
            WorkoutLog.day_exercise_id == day_exercise_id,
            WorkoutLog.date == target_date,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        log = WorkoutLog(user_id=user_id, day_exercise_id=day_exercise_id, date=target_date)
    log.completed = True
    log.actual_sets = sets
    log.actual_reps = reps
    log.actual_weight = weight
    session.add(log)
    await session.commit()
    return log


async def get_logs_for_day(session: AsyncSession, user_id: int, target_date: date) -> list[WorkoutLog]:
    result = await session.execute(
        select(WorkoutLog).where(WorkoutLog.user_id == user_id, WorkoutLog.date == target_date)
    )
    return list(result.scalars().all())


# ---------- Харчування ----------

async def add_meal(
    session: AsyncSession,
    user_id: int,
    name: str,
    calories: float,
    protein: float,
    fat: float,
    carbs: float,
    target_date: date | None = None,
) -> Meal:
    meal = Meal(
        user_id=user_id,
        name=name,
        calories=calories,
        protein=protein,
        fat=fat,
        carbs=carbs,
        date=target_date or date.today(),
    )
    session.add(meal)
    await session.commit()
    return meal


async def get_meals_for_day(session: AsyncSession, user_id: int, target_date: date) -> list[Meal]:
    result = await session.execute(
        select(Meal).where(Meal.user_id == user_id, Meal.date == target_date)
    )
    return list(result.scalars().all())


# ---------- Персональна база продуктів ----------

async def add_product(
    session: AsyncSession,
    user_id: int,
    name: str,
    calories: float,
    protein: float,
    fat: float,
    carbs: float,
) -> Product:
    product = Product(
        user_id=user_id, name=name, calories=calories, protein=protein, fat=fat, carbs=carbs
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def get_products_for_user(session: AsyncSession, user_id: int) -> list[Product]:
    result = await session.execute(
        select(Product).where(Product.user_id == user_id).order_by(Product.name)
    )
    return list(result.scalars().all())


async def get_product_by_id(session: AsyncSession, user_id: int, product_id: int) -> Product | None:
    result = await session.execute(
        select(Product).where(Product.id == product_id, Product.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def delete_product(session: AsyncSession, user_id: int, product_id: int) -> bool:
    product = await get_product_by_id(session, user_id, product_id)
    if product is None:
        return False
    await session.delete(product)
    await session.commit()
    return True


# ---------- Прогрес ----------

async def add_weight_log(session: AsyncSession, user_id: int, weight: float) -> WeightLog:
    log = WeightLog(user_id=user_id, weight=weight, date=date.today())
    session.add(log)
    user = await session.get(User, user_id)
    if user:
        user.weight = weight
        session.add(user)
    await session.commit()
    return log


async def get_weight_history(session: AsyncSession, user_id: int) -> list[WeightLog]:
    result = await session.execute(
        select(WeightLog).where(WeightLog.user_id == user_id).order_by(WeightLog.date)
    )
    return list(result.scalars().all())


async def get_completed_workouts_count(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(WorkoutLog).where(WorkoutLog.user_id == user_id, WorkoutLog.completed.is_(True))
    )
    return len(result.scalars().all())


# ---------- Нагадування ----------

async def get_all_users_with_reminders(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User)
        .where(User.is_registered.is_(True))
        .options(selectinload(User.reminder_settings))
    )
    return list(result.scalars().all())


async def get_reminder_settings(session: AsyncSession, user_id: int) -> ReminderSettings | None:
    result = await session.execute(
        select(ReminderSettings).where(ReminderSettings.user_id == user_id)
    )
    return result.scalar_one_or_none()
