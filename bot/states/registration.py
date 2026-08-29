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


class PlanEditing(StatesGroup):
    """Спільні стани для додавання вправи в день, зміни підходів/повторень
    існуючої вправи та запису позапланового тренування — конкретна дія
    зберігається в FSM-даних під ключем "action" ("add" / "edit" / "adhoc";
    заміна вправи ("swap") обходиться без введення тексту й у ці стани не заходить)."""

    waiting_sets = State()
    waiting_reps = State()
    waiting_weight = State()


class NutritionLogging(StatesGroup):
    waiting_name = State()
    waiting_calories = State()
    waiting_protein = State()
    waiting_fat = State()
    waiting_carbs = State()
    waiting_photo = State()


class MealFromProduct(StatesGroup):
    waiting_grams = State()


class ProductManagement(StatesGroup):
    waiting_name = State()
    waiting_calories = State()
    waiting_protein = State()
    waiting_fat = State()
    waiting_carbs = State()


class WeightLogging(StatesGroup):
    waiting_weight = State()


class ReminderTimeInput(StatesGroup):
    waiting_time = State()
    waiting_water_interval = State()
