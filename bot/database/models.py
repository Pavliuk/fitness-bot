"""SQLAlchemy-моделі бази даних."""
import enum
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Gender(str, enum.Enum):
    male = "male"
    female = "female"


class Goal(str, enum.Enum):
    weight_loss = "weight_loss"          # схуднення
    muscle_gain = "muscle_gain"          # набір маси
    endurance = "endurance"              # витривалість


class Level(str, enum.Enum):
    beginner = "beginner"                # початківець
    intermediate = "intermediate"        # середній
    advanced = "advanced"                # просунутий


class MuscleGroup(str, enum.Enum):
    chest = "chest"
    back = "back"
    legs = "legs"
    shoulders = "shoulders"
    arms = "arms"
    core = "core"
    full_body = "full_body"
    cardio = "cardio"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    gender: Mapped[Gender | None] = mapped_column(Enum(Gender), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)  # кг
    height: Mapped[float | None] = mapped_column(Float, nullable=True)  # см
    goal: Mapped[Goal | None] = mapped_column(Enum(Goal), nullable=True)
    level: Mapped[Level | None] = mapped_column(Enum(Level), nullable=True)

    is_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    workout_plans: Mapped[list["WorkoutPlan"]] = relationship(back_populates="user")
    workout_logs: Mapped[list["WorkoutLog"]] = relationship(back_populates="user")
    meals: Mapped[list["Meal"]] = relationship(back_populates="user")
    products: Mapped[list["Product"]] = relationship(back_populates="user")
    weight_logs: Mapped[list["WeightLog"]] = relationship(back_populates="user")
    reminder_settings: Mapped["ReminderSettings"] = relationship(
        back_populates="user", uselist=False
    )


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    muscle_group: Mapped[MuscleGroup] = mapped_column(Enum(MuscleGroup))
    media_url: Mapped[str | None] = mapped_column(String(256), nullable=True)  # відео/GIF
    difficulty: Mapped[Level] = mapped_column(Enum(Level), default=Level.beginner)

    day_links: Mapped[list["WorkoutDayExercise"]] = relationship(back_populates="exercise")


class WorkoutPlan(Base):
    __tablename__ = "workout_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    goal: Mapped[Goal] = mapped_column(Enum(Goal))
    level: Mapped[Level] = mapped_column(Enum(Level))
    duration_weeks: Mapped[int] = mapped_column(Integer, default=4)
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="workout_plans")
    days: Mapped[list["WorkoutDay"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class WorkoutDay(Base):
    """Один тренувальний день у межах плану (тиждень + день тижня)."""

    __tablename__ = "workout_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("workout_plans.id"))
    week_number: Mapped[int] = mapped_column(Integer)          # 1..duration_weeks
    day_of_week: Mapped[int] = mapped_column(Integer)          # 0=Пн ... 6=Нд
    focus: Mapped[str] = mapped_column(String(64), default="")  # напр. "Ноги + кор"
    is_rest_day: Mapped[bool] = mapped_column(Boolean, default=False)

    plan: Mapped["WorkoutPlan"] = relationship(back_populates="days")
    exercises: Mapped[list["WorkoutDayExercise"]] = relationship(
        back_populates="day", cascade="all, delete-orphan", order_by="WorkoutDayExercise.order"
    )


class WorkoutDayExercise(Base):
    """Конкретна вправа в межах тренувального дня із цільовими підходами/повтореннями."""

    __tablename__ = "workout_day_exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("workout_days.id"))
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"))
    order: Mapped[int] = mapped_column(Integer, default=0)
    target_sets: Mapped[int] = mapped_column(Integer, default=3)
    target_reps: Mapped[str] = mapped_column(String(32), default="10-12")

    day: Mapped["WorkoutDay"] = relationship(back_populates="exercises")
    exercise: Mapped["Exercise"] = relationship(back_populates="day_links")
    logs: Mapped[list["WorkoutLog"]] = relationship(back_populates="day_exercise")


class WorkoutLog(Base):
    """Відмітки про фактичне виконання вправи користувачем."""

    __tablename__ = "workout_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    day_exercise_id: Mapped[int] = mapped_column(ForeignKey("workout_day_exercises.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    actual_sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_reps: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actual_weight: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped["User"] = relationship(back_populates="workout_logs")
    day_exercise: Mapped["WorkoutDayExercise"] = relationship(back_populates="logs")


class Meal(Base):
    """Запис у щоденнику харчування."""

    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    name: Mapped[str] = mapped_column(String(128))
    calories: Mapped[float] = mapped_column(Float, default=0)
    protein: Mapped[float] = mapped_column(Float, default=0)
    fat: Mapped[float] = mapped_column(Float, default=0)
    carbs: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="meals")


class Product(Base):
    """Персональний продукт користувача (БЖУ на 100 г) для швидкого додавання прийомів їжі."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(128))
    calories: Mapped[float] = mapped_column(Float, default=0)  # на 100 г
    protein: Mapped[float] = mapped_column(Float, default=0)
    fat: Mapped[float] = mapped_column(Float, default=0)
    carbs: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="products")


class WeightLog(Base):
    """Історія зміни ваги для графіка прогресу."""

    __tablename__ = "weight_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    weight: Mapped[float] = mapped_column(Float)

    user: Mapped["User"] = relationship(back_populates="weight_logs")


class ReminderSettings(Base):
    """Налаштування нагадувань користувача."""

    __tablename__ = "reminder_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)

    workout_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    workout_time: Mapped[time] = mapped_column(Time, default=time(18, 0))

    water_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    water_interval_min: Mapped[int] = mapped_column(Integer, default=120)
    water_start: Mapped[time] = mapped_column(Time, default=time(8, 0))
    water_end: Mapped[time] = mapped_column(Time, default=time(22, 0))

    meals_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    breakfast_time: Mapped[time] = mapped_column(Time, default=time(9, 0))
    lunch_time: Mapped[time] = mapped_column(Time, default=time(13, 0))
    dinner_time: Mapped[time] = mapped_column(Time, default=time(19, 0))

    user: Mapped["User"] = relationship(back_populates="reminder_settings")
