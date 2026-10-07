from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ChatMemberStatus
from bot.database import claim_freebie, get_freebie_status, get_products
from bot.config import DAILY_FREEBIE_AMOUNT, FREEBIE_CHANNEL
from bot.utils.ui import DIVIDER, green, pe, sky

router = Router()

CHANNEL_URL = f"https://t.me/{FREEBIE_CHANNEL.lstrip('@')}"


async def is_channel_member(bot: Bot, user_id: int) -> bool:
    """Return True if user is a member/admin/owner of FREEBIE_CHANNEL."""
    try:
        member = await bot.get_chat_member(chat_id=FREEBIE_CHANNEL, user_id=user_id)
        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.RESTRICTED,
        )
    except Exception:
        return False


def format_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


@router.callback_query(F.data == "menu:freebies")
async def cb_freebies(callback: CallbackQuery, db_user: dict):
    # Fetch daily bonus status + all free products — no channel gate here
    status = await get_freebie_status(db_user["id"])
    free_products = [p for p in await get_products(active_only=True) if p.get("price", 1) == 0.0]

    streak = status["streak"]
    total = status["total_claimed"]
    can_claim = status["can_claim"]
    seconds_left = status["seconds_left"]

    next_bonus = DAILY_FREEBIE_AMOUNT * (1 + streak * 0.1)
    streak_display = "🔥 " * min(streak, 5) + (f"x{streak}" if streak > 0 else "")
    streak_line = f"🔥 Streak: <b>{streak_display}</b>\n" if streak > 0 else ""

    if can_claim:
        bonus_status = f"✅ <b>Ready to claim!</b>  Bonus: <b>${next_bonus:.2f}</b>"
    else:
        time_left = format_time(seconds_left)
        bonus_status = f"⏳ Next claim in: <b>{time_left}</b>"

    # Build free products list text
    if free_products:
        prod_lines = "\n".join(
            f"{p.get('logo') or '🆓'} <b>{p['name']}</b> — "
            + ("<b>available</b>" if (p.get("stock_count", 0) or 0) > 0 else "<i>sold out</i>")
            for p in free_products
        )
        free_section = (
            f"{DIVIDER}\n{pe('gift')} <b>FREE TOOLS</b>\n\n{prod_lines}\n\n"
        )
    else:
        free_section = ""

    text = (
        f"{pe('gift')} <b>FREEBIES</b> {pe('sparkles')}\n"
        f"{DIVIDER}\n"
        f"📅 <b>Daily Bonus</b>\n\n"
        f"{streak_line}"
        f"💰 Total earned: <b>${total:.2f}</b>\n"
        f"{bonus_status}\n\n"
        f"{free_section}"
        f"{DIVIDER}\n"
        f"<i>Channel membership is checked when you claim.</i>"
    )

    builder = InlineKeyboardBuilder()
    if can_claim:
        builder.row(green(f"{pe('gift')} Claim Daily Bonus", callback_data="freebies:claim"))
    else:
        builder.row(InlineKeyboardButton(
            text=f"⏳ Next bonus in {format_time(seconds_left)}", callback_data="shop:noop"))
    from bot.utils.ui import stock_btn
    for p in free_products:
        logo = p.get("logo") or "🆓"
        has_stock = (p.get("stock_count", 0) or 0) > 0
        tail = "FREE" if has_stock else "SOLD OUT"
        builder.row(stock_btn(f"{logo} {p['name']} — {tail}", has_stock,
                              callback_data=f"shop:prod:{p['id']}"))
    builder.row(sky("🏠 Main Menu", callback_data="menu:main"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "freebies:claim")
async def cb_claim(callback: CallbackQuery, db_user: dict):
    # Double-check channel membership before granting
    joined = await is_channel_member(callback.bot, callback.from_user.id)
    if not joined:
        await callback.answer(
            f"❌ You must join {FREEBIE_CHANNEL} first!", show_alert=True
        )
        return

    result = await claim_freebie(db_user["id"], DAILY_FREEBIE_AMOUNT)
    if not result["success"]:
        time_left = format_time(result["seconds_left"])
        await callback.answer(f"⏳ Come back in {time_left}!", show_alert=True)
        return

    amount = result["amount"]
    streak = result["streak"]

    streak_msg = f"🔥 Streak x{streak}! " if streak > 1 else ""
    text = (
        f"🎉 <b>Daily Bonus Claimed!</b>\n\n"
        f"{streak_msg}You received: <b>+${amount:.2f}</b>\n\n"
        f"{'🔥 ' * min(streak, 7)}\n"
        f"Current streak: <b>{streak} days</b>\n\n"
        f"Come back tomorrow for another bonus!\n"
        f"{'Streak bonus: +' + str(int((streak - 1) * 10)) + '%' if streak > 1 else 'Keep your streak for bigger bonuses!'}"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer(f"🎁 +${amount:.4f} claimed!")
