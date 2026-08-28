"""Клавіатури для розділу тренувань."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import WorkoutDayExercise, WorkoutLog


def checklist_kb(
    day_exercises: list[WorkoutDayExercise], logs_by_exercise: dict[int, WorkoutLog]
) -> InlineKeyboardMarkup:
    rows = []
    for de in day_exercises:
        log = logs_by_exercise.get(de.id)
        done = log.completed if log else False
        mark = "✅" if done else "⬜️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {de.exercise.name}",
                    callback_data=f"toggle:{de.id}",
                ),
                InlineKeyboardButton(text="✍️ Лог", callback_data=f"logset:{de.id}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_setup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 4 тижні", callback_data="plan_weeks:4")],
            [InlineKeyboardButton(text="🗓 8 тижнів", callback_data="plan_weeks:8")],
            [InlineKeyboardButton(text="🔁 Перегенерувати поточний план", callback_data="plan_regen")],
        ]
    )
