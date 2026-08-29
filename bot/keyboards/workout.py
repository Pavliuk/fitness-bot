"""Клавіатури для розділу тренувань."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import Exercise, WorkoutDayExercise, WorkoutLog

MUSCLE_GROUP_LABELS = {
    "chest": "Груди",
    "back": "Спина",
    "legs": "Ноги",
    "shoulders": "Плечі",
    "arms": "Руки",
    "core": "Кор",
    "full_body": "Все тіло",
    "cardio": "Кардіо",
}


def checklist_kb(
    day_exercises: list[WorkoutDayExercise], logs_by_exercise: dict[int, WorkoutLog], is_rest: bool
) -> InlineKeyboardMarkup:
    rows = []
    for de in day_exercises:
        log = logs_by_exercise.get(de.id)
        done = log.completed if log else False
        mark = "✅" if done else "⬜️"
        rows.append(
            [InlineKeyboardButton(text=f"{mark} {de.exercise.name}", callback_data=f"toggle:{de.id}")]
        )
        rows.append(
            [
                InlineKeyboardButton(text="ℹ️ Техніка", callback_data=f"exercise_info:{de.exercise.id}"),
                InlineKeyboardButton(text="✍️ Лог", callback_data=f"logset:{de.id}"),
                InlineKeyboardButton(text="✏️ Керувати", callback_data=f"de_manage:{de.id}"),
            ]
        )

    rows.append([InlineKeyboardButton(text="➕ Додати вправу до дня", callback_data="wex_add_start")])
    if is_rest:
        rows.append([InlineKeyboardButton(text="🏋️ Зробити сьогодні тренувальним", callback_data="day_make_training")])
    else:
        rows.append([InlineKeyboardButton(text="😴 Позначити сьогодні вихідним", callback_data="day_make_rest")])
    rows.append([InlineKeyboardButton(text="🔁 Позапланове тренування", callback_data="adhoc_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def muscle_group_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"wex_group:{key}")]
            for key, label in MUSCLE_GROUP_LABELS.items()
        ]
    )


def exercise_pick_kb(exercises: list[Exercise]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ex.name, callback_data=f"wex_pick:{ex.id}")] for ex in exercises
        ]
    )


def day_exercise_manage_kb(day_exercise_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Замінити вправу", callback_data=f"de_swap:{day_exercise_id}")],
            [InlineKeyboardButton(text="🔢 Змінити підходи/повторення", callback_data=f"de_edit:{day_exercise_id}")],
            [InlineKeyboardButton(text="🗑 Видалити з дня", callback_data=f"de_delete:{day_exercise_id}")],
        ]
    )


def plan_setup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 4 тижні", callback_data="plan_weeks:4")],
            [InlineKeyboardButton(text="🗓 8 тижнів", callback_data="plan_weeks:8")],
            [InlineKeyboardButton(text="🔁 Перегенерувати поточний план", callback_data="plan_regen")],
        ]
    )
