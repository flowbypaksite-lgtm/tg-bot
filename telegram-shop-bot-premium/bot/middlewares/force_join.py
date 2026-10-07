"""Force channel join middleware.

When enabled from the admin panel (Admin ➜ Force Join), users must be members
of every configured channel before they can use the bot.  Admins are always
exempt, and the check is skipped entirely while the feature is off, so it costs
nothing when unused.
"""
from typing import Any, Awaitable, Callable, Dict, List

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database import get_force_join_config
from bot.utils.ui import DIVIDER, green, pe, sky

ALLOWED_CALLBACKS = ("fj:check",)


async def _is_member(bot, channel: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status in ("creator", "administrator", "member", "restricted")
    except Exception:
        # If the bot can't read the channel we don't lock the user out.
        return True


async def missing_channels(bot, user_id: int, channels: List[str]) -> List[str]:
    missing = []
    for channel in channels:
        if not await _is_member(bot, channel, user_id):
            missing.append(channel)
    return missing


def join_prompt_kb(channels: List[str]):
    builder = InlineKeyboardBuilder()
    for channel in channels:
        username = channel.lstrip("@")
        url = channel if channel.startswith("http") else f"https://t.me/{username}"
        builder.row(sky(f"{pe('megaphone')} Join {channel}", url=url))
    builder.row(green(f"{pe('check')} I Joined — Verify", callback_data="fj:check"))
    return builder.as_markup()


def join_prompt_text(channels: List[str]) -> str:
    listed = "\n".join(f"• {c}" for c in channels)
    return (
        f"{pe('lock')} <b>MEMBERS ONLY</b>\n"
        f"{DIVIDER}\n"
        f"Please join our channel(s) to unlock the bot:\n\n"
        f"{listed}\n\n"
        f"{DIVIDER}\n"
        f"{pe('bolt')} Tap <b>I Joined — Verify</b> after joining."
    )


class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        from bot.config import ADMIN_IDS

        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)

        if user.id in ADMIN_IDS:
            return await handler(event, data)

        config = await get_force_join_config()
        if not config["enabled"] or not config["channels"]:
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and (event.data or "") in ALLOWED_CALLBACKS:
            return await handler(event, data)

        missing = await missing_channels(event.bot, user.id, config["channels"])
        if not missing:
            return await handler(event, data)

        text = join_prompt_text(missing)
        keyboard = join_prompt_kb(missing)
        if isinstance(event, Message):
            await event.answer(text, reply_markup=keyboard, parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            await event.answer("🔒 Join the channel first!", show_alert=True)
            try:
                await event.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            except Exception:
                await event.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return None
