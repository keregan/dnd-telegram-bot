from __future__ import annotations

from pathlib import Path

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message


async def edit_or_answer(message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Edit a text message when possible; otherwise send a new message.

    Telegram cannot edit a photo message into a text message. This helper keeps inline
    navigation stable even when the previous screen was sent as a photo with caption.
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

def resolve_photo_source(image_ref: str | None):
    if not image_ref:
        return None
    raw = str(image_ref).strip()
    if not raw:
        return None
    path = Path(raw)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(PROJECT_ROOT / path)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return FSInputFile(str(candidate))
    return raw


async def answer_with_optional_photo(message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None, image_ref: str | None = None) -> None:
    photo = resolve_photo_source(image_ref)
    if photo is None:
        await message.answer(text, reply_markup=reply_markup)
        return
    try:
        await message.answer_photo(photo, caption=text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup)
