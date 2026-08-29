"""Допоміжні функції доступу до БД (простий шар "репозиторію")."""
from datetime import date

from sqlalchemy import select
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

async def get_or_create_user(session: AsyncSession, tg_id: int, username: str | None) -> User:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(tg_id=tg_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_user_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    return result.scalar_one_or_none()


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


async def bulk_add_exercises(session: AsyncSession, exercises: list[dict]) -> None:
    """Наповнює таблицю exercises з assets/exercises.json, якщо вона порожня."""
    existing = await session.execute(select(Exercise.id).limit(1))
    if existing.scalar_one_or_none() is not None:
        return
    for item in exercises:
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
