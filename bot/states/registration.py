"""FSM-стани для анкети реєстрації користувача."""
from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    gender = State()
    age = State()
    weight = State()
    height = State()
    goal = State()
    level = State()


class WorkoutLogging(StatesGroup):
    waiting_sets = State()
    waiting_reps = State()
    waiting_weight = State()


class NutritionLogging(StatesGroup):
    waiting_name = State()
    waiting_calories = State()
    waiting_protein = State()
    waiting_fat = State()
    waiting_carbs = State()


class WeightLogging(StatesGroup):
    waiting_weight = State()
