"""Розрахунок орієнтовної денної норми калорій та БЖУ (формула Міффліна-Сан Жеора)."""
from bot.database.models import Gender, Goal

# Коефіцієнт активності — фіксований середній рівень, бо детальної анкети
# про рівень активності поза тренуваннями в ТЗ немає. Можна розширити анкету пізніше.
ACTIVITY_FACTOR = 1.4

GOAL_CALORIE_ADJUSTMENT = {
    Goal.weight_loss: -0.15,   # дефіцит 15%
    Goal.muscle_gain: 0.10,    # профіцит 10%
    Goal.endurance: 0.0,
}

# г білка/жиру/вуглеводів на кг ваги, залежно від цілі
MACROS_PER_KG = {
    Goal.weight_loss: {"protein": 2.0, "fat": 0.9, "carbs": 2.5},
    Goal.muscle_gain: {"protein": 1.8, "fat": 1.0, "carbs": 4.0},
    Goal.endurance: {"protein": 1.6, "fat": 1.0, "carbs": 4.5},
}


def calculate_bmr(gender: Gender, weight_kg: float, height_cm: float, age: int) -> float:
    if gender == Gender.male:
        return 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    return 10 * weight_kg + 6.25 * height_cm - 5 * age - 161


def calculate_daily_targets(
    gender: Gender, weight_kg: float, height_cm: float, age: int, goal: Goal
) -> dict:
    bmr = calculate_bmr(gender, weight_kg, height_cm, age)
    tdee = bmr * ACTIVITY_FACTOR
    target_calories = tdee * (1 + GOAL_CALORIE_ADJUSTMENT[goal])

    macros = MACROS_PER_KG[goal]
    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "target_calories": round(target_calories),
        "protein_g": round(macros["protein"] * weight_kg),
        "fat_g": round(macros["fat"] * weight_kg),
        "carbs_g": round(macros["carbs"] * weight_kg),
    }
