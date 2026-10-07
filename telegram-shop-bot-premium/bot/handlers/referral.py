from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from bot.database import get_referrals, get_referral_earnings, get_setting
import os

router = Router()


@router.callback_query(F.data == "menu:referral")
async def cb_referral(callback: CallbackQuery, db_user: dict):
    # Referral code = user's own Telegram ID
    bot_username = os.environ.get("BOT_USERNAME", "yourbot")
    referral_link = f"https://t.me/{bot_username}?start={db_user['telegram_id']}"
    referral_bonus = float(await get_setting("referral_bonus") or "0.05")

    referrals = await get_referrals(db_user["id"])
    total_refs = len(referrals)
    paid_refs = sum(1 for r in referrals if r.get("bonus_paid"))
    pending_refs = total_refs - paid_refs
    total_earned = await get_referral_earnings(db_user["id"])

    recent_lines = []
    for ref in referrals[:5]:
        name = ref.get("first_name") or ref.get("username") or "Friend"
        date = str(ref.get("joined_at", ""))[:10]
        status = "✅" if ref.get("bonus_paid") else "⏳"
        recent_lines.append(f"  {status} {name} — {date}")

    recent_section = ""
    if recent_lines:
        recent_section = "\n<b>Recent Referrals:</b>\n" + "\n".join(recent_lines) + "\n\n"

    text = (
        f"🔗 <b>Referral Program</b>\n\n"
        f"Invite friends and earn <b>${referral_bonus:.2f}</b> for each one who makes their first purchase!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Referrals: <b>{total_refs}</b>\n"
        f"✅ Bonuses Earned: <b>{paid_refs}</b>\n"
        f"💰 Total Earned: <b>${total_earned:.2f}</b>\n"
        f"⏳ Pending: <b>{pending_refs}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{recent_section}"
        f"📎 <b>Your Referral Link:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"Share your link and earn when friends join!"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📤 Share Referral Link",
            switch_inline_query=(
                f"🛍️ Join PremiumShop and shop digital products instantly!\n"
                f"Use my link: {referral_link}"
            ),
        )
    )
    builder.row(InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:referral"))
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()
