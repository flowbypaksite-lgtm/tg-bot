from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from bot.database import get_or_create_user


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        referral_code = None

        if isinstance(event, Message):
            tg_user = event.from_user
            # Referral code is the referrer's Telegram numeric ID, passed via /start <id>
            if event.text and event.text.startswith("/start "):
                parts = event.text.split(maxsplit=1)
                if len(parts) > 1:
                    code = parts[1].strip()
                    if code.isdigit():
                        referral_code = code  # referrer's telegram_id as string
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user
        else:
            return await handler(event, data)

        if tg_user:
            db_user = await get_or_create_user(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                referral_code=referral_code,
            )
            data["db_user"] = db_user

            if db_user.get("is_banned"):
                if isinstance(event, Message):
                    await event.answer("🚫 You have been banned from this bot.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 You are banned.", show_alert=True)
                return

        return await handler(event, data)
