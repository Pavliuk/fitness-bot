"""Оцінка БЖУ/калорійності страви на фото через vision-запит до Claude."""
import base64
import logging

import anthropic
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_MODEL = "claude-opus-5"

_PROMPT = (
    "Подивись на фото їжі та оціни її поживну цінність для ВСІЄЇ видимої "
    "порції (не на 100 г — саме на те, що видно на фото). Якщо на фото "
    "немає їжі, встанови is_food=false і залиш нулі в решті полів. Назву "
    "страви напиши українською, коротко. Оцінюй реалістично на основі "
    "типового рецепта та видимого розміру порції. У полі note коротко "
    "поясни, на чому базується оцінка, або на що зважати (напр. \"оцінка "
    "приблизна, соус міг додати калорій\")."
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
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    client = anthropic.AsyncAnthropic()

    try:
        response = await client.messages.parse(
            model=_MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }],
            output_format=NutritionEstimate,
        )
    except anthropic.AuthenticationError as exc:
        logger.error("Food vision: немає дійсного ANTHROPIC_API_KEY")
        raise FoodVisionError(
            "Розпізнавання фото ще не налаштоване адміністратором бота."
        ) from exc
    except anthropic.RateLimitError as exc:
        raise FoodVisionError(
            "Забагато запитів на розпізнавання фото зараз, спробуй за хвилину."
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise FoodVisionError(
            "Немає з'єднання для розпізнавання фото, спробуй пізніше."
        ) from exc
    except anthropic.APIStatusError as exc:
        logger.exception("Food vision: помилка API")
        raise FoodVisionError("Не вдалося розпізнати фото, спробуй ще раз.") from exc

    estimate = response.parsed_output
    if estimate is None:
        raise FoodVisionError("Не вдалося розпізнати фото, спробуй ще раз.")
    return estimate
