from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message


async def edit_or_answer(message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Edit a text message when possible; otherwise send a new message.

    Telegram cannot edit a photo message into a text message. This helper keeps inline
    navigation stable even when the previous screen was sent as a photo with caption.
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup)
