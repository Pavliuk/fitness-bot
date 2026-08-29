"""Оцінка БЖУ/калорійності страви на фото через Gemini Vision (безкоштовний рівень)."""
import json
import logging

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.6-flash"

_PROMPT = (
    "Подивись на фото їжі та оціни її поживну цінність для ВСІЄЇ видимої "
    "порції (не на 100 г — саме на те, що видно на фото). Якщо на фото "
    "немає їжі, встанови is_food=false і залиш нулі в решті полів. Назву "
    "страви напиши українською, коротко. Оцінюй реалістично на основі "
    "типового рецепта та видимого розміру порції. У полі note коротко "
    "поясни, на чому базується оцінка, або на що зважати (напр. \"оцінка "
    "приблизна, соус міг додати калорій\"). Відповідай лише JSON-об'єктом "
    "без додаткового тексту."
)


class NutritionEstimate(BaseModel):
    is_food: bool
    food_name: str
    calories: float
    protein_g: float
    fat_g: float
    carbs_g: float
    note: str


class FoodVisionError(Exception):
    """Не вдалося отримати оцінку БЖУ з фото (мережа, ліміти, відсутній ключ тощо)."""


async def estimate_nutrition_from_photo(
    image_bytes: bytes, media_type: str = "image/jpeg"
) -> NutritionEstimate:
    client = genai.Client()  # читає GOOGLE_API_KEY / GEMINI_API_KEY зі середовища

    try:
        response = await client.aio.models.generate_content(
            model=_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=media_type),
                _PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=NutritionEstimate.model_json_schema(),
            ),
        )
    except errors.ClientError as exc:
        if exc.code in (401, 403):
            logger.error("Food vision: немає дійсного GEMINI_API_KEY")
            raise FoodVisionError(
                "Розпізнавання фото ще не налаштоване адміністратором бота."
            ) from exc
        if exc.code == 429:
            raise FoodVisionError(
                "Забагато запитів на розпізнавання фото зараз, спробуй за хвилину."
            ) from exc
        logger.exception("Food vision: помилка API (%s)", exc.code)
        raise FoodVisionError("Не вдалося розпізнати фото, спробуй ще раз.") from exc
    except errors.ServerError as exc:
        logger.exception("Food vision: серверна помилка API")
        raise FoodVisionError("Не вдалося розпізнати фото, спробуй ще раз.") from exc

    if not response.text:
        raise FoodVisionError("Не вдалося розпізнати фото, спробуй ще раз.")

    try:
        return NutritionEstimate.model_validate(json.loads(response.text))
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.exception("Food vision: не вдалося розпарсити відповідь")
        raise FoodVisionError("Не вдалося розпізнати фото, спробуй ще раз.") from exc
