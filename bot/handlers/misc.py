"""Розважальні хендлери, не пов'язані з тренуваннями чи харчуванням."""
from pathlib import Path

from aiogram import F, Router
from aiogram.types import FSInputFile, Message

router = Router(name="misc")

_MEME_VIDEO_PATH = Path(__file__).resolve().parents[2] / "data" / "media" / "delay_gryaz.mp4"


@router.message(F.text == "😂 Делай грязь")
async def send_degrees_meme(message: Message):
    await message.answer_video(FSInputFile(_MEME_VIDEO_PATH))
