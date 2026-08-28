"""
Генератор програм тренувань.

Логіка (базова, легко розширювана):
1. Для кожної пари (ціль, рівень) визначено шаблон тижня — список тренувальних
   днів тижня (0=Пн..6=Нд) із фокусними групами м'язів та кількістю вправ.
2. Кількість підходів/повторень залежить від цілі:
   - схуднення / витривалість -> більше повторень, менше відпочинку (12-20 повт.)
   - набір маси -> менше повторень, більша вага (6-10 повт.)
3. Вправи в межах групи м'язів ротуються по тижнях, щоб уникнути одноманітності
   (тиждень 1 бере вправи [0,1], тиждень 2 бере [1,2] і т.д. по колу).
"""
import random
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    Exercise,
    Goal,
    Level,
    MuscleGroup,
    WorkoutDay,
    WorkoutDayExercise,
    WorkoutPlan,
)
from bot.database.requests import get_all_exercises

# Скільки вправ на групу м'язів брати в один тренувальний день
EXERCISES_PER_GROUP = 2

# Шаблони тижня: {(goal, level): [{"day_of_week": int, "focus": str, "groups": [...]}]}
WEEK_TEMPLATES: dict[tuple[Goal, Level], list[dict]] = {
    (Goal.weight_loss, Level.beginner): [
        {"day_of_week": 0, "focus": "Все тіло + кардіо", "groups": [MuscleGroup.full_body, MuscleGroup.cardio]},
        {"day_of_week": 2, "focus": "Кор + кардіо", "groups": [MuscleGroup.core, MuscleGroup.cardio]},
        {"day_of_week": 4, "focus": "Все тіло", "groups": [MuscleGroup.full_body, MuscleGroup.legs]},
    ],
    (Goal.weight_loss, Level.intermediate): [
        {"day_of_week": 0, "focus": "Верх тіла + кардіо", "groups": [MuscleGroup.chest, MuscleGroup.back, MuscleGroup.cardio]},
        {"day_of_week": 1, "focus": "Кардіо (HIIT)", "groups": [MuscleGroup.cardio, MuscleGroup.core]},
        {"day_of_week": 3, "focus": "Низ тіла", "groups": [MuscleGroup.legs, MuscleGroup.core]},
        {"day_of_week": 5, "focus": "Все тіло", "groups": [MuscleGroup.full_body, MuscleGroup.cardio]},
    ],
    (Goal.weight_loss, Level.advanced): [
        {"day_of_week": 0, "focus": "Верх тіла + HIIT", "groups": [MuscleGroup.chest, MuscleGroup.back, MuscleGroup.cardio]},
        {"day_of_week": 1, "focus": "HIIT", "groups": [MuscleGroup.cardio, MuscleGroup.core]},
        {"day_of_week": 2, "focus": "Низ тіла", "groups": [MuscleGroup.legs, MuscleGroup.core]},
        {"day_of_week": 4, "focus": "Все тіло", "groups": [MuscleGroup.full_body, MuscleGroup.shoulders]},
        {"day_of_week": 5, "focus": "HIIT + кор", "groups": [MuscleGroup.cardio, MuscleGroup.core]},
    ],
    (Goal.muscle_gain, Level.beginner): [
        {"day_of_week": 0, "focus": "Верх тіла", "groups": [MuscleGroup.chest, MuscleGroup.back, MuscleGroup.arms]},
        {"day_of_week": 2, "focus": "Низ тіла", "groups": [MuscleGroup.legs, MuscleGroup.core]},
        {"day_of_week": 4, "focus": "Все тіло", "groups": [MuscleGroup.full_body, MuscleGroup.shoulders]},
    ],
    (Goal.muscle_gain, Level.intermediate): [
        {"day_of_week": 0, "focus": "Груди + трицепс", "groups": [MuscleGroup.chest, MuscleGroup.arms]},
        {"day_of_week": 1, "focus": "Спина + біцепс", "groups": [MuscleGroup.back, MuscleGroup.arms]},
        {"day_of_week": 3, "focus": "Ноги", "groups": [MuscleGroup.legs, MuscleGroup.core]},
        {"day_of_week": 5, "focus": "Плечі + кор", "groups": [MuscleGroup.shoulders, MuscleGroup.core]},
    ],
    (Goal.muscle_gain, Level.advanced): [
        {"day_of_week": 0, "focus": "Груди", "groups": [MuscleGroup.chest]},
        {"day_of_week": 1, "focus": "Спина", "groups": [MuscleGroup.back]},
        {"day_of_week": 2, "focus": "Ноги", "groups": [MuscleGroup.legs]},
        {"day_of_week": 3, "focus": "Плечі", "groups": [MuscleGroup.shoulders]},
        {"day_of_week": 4, "focus": "Руки + кор", "groups": [MuscleGroup.arms, MuscleGroup.core]},
        {"day_of_week": 5, "focus": "Все тіло (легко)", "groups": [MuscleGroup.full_body]},
    ],
    (Goal.endurance, Level.beginner): [
        {"day_of_week": 0, "focus": "Кардіо (легко)", "groups": [MuscleGroup.cardio]},
        {"day_of_week": 2, "focus": "Все тіло", "groups": [MuscleGroup.full_body, MuscleGroup.core]},
        {"day_of_week": 4, "focus": "Кардіо", "groups": [MuscleGroup.cardio]},
    ],
    (Goal.endurance, Level.intermediate): [
        {"day_of_week": 0, "focus": "Кардіо", "groups": [MuscleGroup.cardio]},
        {"day_of_week": 1, "focus": "Кор + все тіло", "groups": [MuscleGroup.core, MuscleGroup.full_body]},
        {"day_of_week": 3, "focus": "Кардіо (інтервали)", "groups": [MuscleGroup.cardio]},
        {"day_of_week": 5, "focus": "Все тіло", "groups": [MuscleGroup.full_body, MuscleGroup.legs]},
    ],
    (Goal.endurance, Level.advanced): [
        {"day_of_week": 0, "focus": "Довге кардіо", "groups": [MuscleGroup.cardio]},
        {"day_of_week": 1, "focus": "Сила + кор", "groups": [MuscleGroup.full_body, MuscleGroup.core]},
        {"day_of_week": 2, "focus": "HIIT", "groups": [MuscleGroup.cardio]},
        {"day_of_week": 4, "focus": "Довге кардіо", "groups": [MuscleGroup.cardio]},
        {"day_of_week": 5, "focus": "Все тіло", "groups": [MuscleGroup.full_body, MuscleGroup.legs]},
    ],
}

# Цільові підходи/повторення залежно від цілі
SETS_REPS_BY_GOAL: dict[Goal, tuple[int, str]] = {
    Goal.weight_loss: (3, "15-20"),
    Goal.muscle_gain: (4, "6-10"),
    Goal.endurance: (3, "20-25"),
}


def _pick_exercises_for_week(
    exercises_by_group: dict[MuscleGroup, list[Exercise]],
    group: MuscleGroup,
    week_number: int,
) -> list[Exercise]:
    """Ротація вправ по тижнях: зсуваємо вікно вибірки, щоб вправи мінялися."""
    pool = exercises_by_group.get(group, [])
    if not pool:
        return []
    if len(pool) <= EXERCISES_PER_GROUP:
        return pool
    offset = (week_number - 1) % len(pool)
    rotated = pool[offset:] + pool[:offset]
    return rotated[:EXERCISES_PER_GROUP]


async def generate_plan(
    session: AsyncSession,
    user_id: int,
    goal: Goal,
    level: Level,
    duration_weeks: int = 4,
    start_date: date | None = None,
) -> WorkoutPlan:
    """Створює новий WorkoutPlan із днями та вправами на весь термін."""
    start_date = start_date or date.today()

    all_exercises = await get_all_exercises(session)
    exercises_by_group: dict[MuscleGroup, list[Exercise]] = {}
    for ex in all_exercises:
        exercises_by_group.setdefault(ex.muscle_group, []).append(ex)
    for group_list in exercises_by_group.values():
        random.Random(42).shuffle(group_list)  # детермінований, але не "по алфавіту" порядок

    template = WEEK_TEMPLATES.get((goal, level))
    if template is None:
        raise ValueError(f"Немає шаблону для цілі={goal} рівня={level}")

    target_sets, target_reps = SETS_REPS_BY_GOAL[goal]

    plan = WorkoutPlan(
        user_id=user_id,
        goal=goal,
        level=level,
        duration_weeks=duration_weeks,
        start_date=start_date,
        is_active=True,
    )
    session.add(plan)
    await session.flush()  # отримуємо plan.id до коміту

    for week_number in range(1, duration_weeks + 1):
        for day_template in template:
            workout_day = WorkoutDay(
                plan_id=plan.id,
                week_number=week_number,
                day_of_week=day_template["day_of_week"],
                focus=day_template["focus"],
                is_rest_day=False,
            )
            session.add(workout_day)
            await session.flush()

            order = 0
            for group in day_template["groups"]:
                for exercise in _pick_exercises_for_week(exercises_by_group, group, week_number):
                    session.add(
                        WorkoutDayExercise(
                            day_id=workout_day.id,
                            exercise_id=exercise.id,
                            order=order,
                            target_sets=target_sets,
                            target_reps=target_reps,
                        )
                    )
                    order += 1

    await session.commit()
    await session.refresh(plan)
    return plan
