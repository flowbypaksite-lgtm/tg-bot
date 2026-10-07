"""Handler for the 'I Joined — Verify' button of the force-join gate."""
from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database import get_force_join_config
from bot.middlewares.force_join import join_prompt_kb, join_prompt_text, missing_channels

router = Router()


@router.callback_query(F.data == "fj:check")
async def cb_force_join_check(callback: CallbackQuery, db_user: dict):
    config = await get_force_join_config()
    channels = config["channels"]
    missing = await missing_channels(callback.bot, callback.from_user.id, channels) if channels else []

    if missing and config["enabled"]:
        await callback.answer("❌ Not joined yet. Please join and try again.", show_alert=True)
        try:
            await callback.message.edit_text(
                join_prompt_text(missing), reply_markup=join_prompt_kb(missing), parse_mode="HTML"
            )
        except Exception:
            pass
        return

    from bot.handlers.start import _build_welcome, build_main_kb
    import os

    bot_username = os.environ.get("BOT_USERNAME", "")
    text = await _build_welcome(callback.from_user, db_user, bot_username)
    kb = await build_main_kb()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML",
                                         disable_web_page_preview=True)
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML",
                                      disable_web_page_preview=True)
    await callback.answer("✅ Verified — welcome!")
