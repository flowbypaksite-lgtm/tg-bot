from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from bot.database import get_user_orders, get_referrals, get_referral_earnings, get_user_total_spent
from bot.config import MEMBERSHIP_TIERS
import os

router = Router()


def profile_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 My Orders", callback_data="profile:orders"),
        InlineKeyboardButton(text="🔗 My Referrals", callback_data="profile:referrals"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))
    return builder.as_markup()


@router.callback_query(F.data == "menu:profile")
async def cb_profile(callback: CallbackQuery, db_user: dict):
    user = db_user
    joined = str(user.get("joined_at", ""))[:10] or "N/A"
    bot_username = os.environ.get("BOT_USERNAME", "yourbot")
    referral_link = f"https://t.me/{bot_username}?start={user['telegram_id']}"

    # Membership tier
    tier_key = user.get("membership_type", "none")
    tier_info = MEMBERSHIP_TIERS.get(tier_key, MEMBERSHIP_TIERS["none"])
    tier_name = tier_info["name"]
    discount = tier_info["discount"]

    # Stats
    orders = await get_user_orders(user["id"])
    total_orders = len(orders)
    total_spent = await get_user_total_spent(user["id"])
    referrals = await get_referrals(user["id"])
    referral_count = len(referrals)
    referral_earnings = await get_referral_earnings(user["id"])

    # Next tier progress
    tiers_ordered = list(MEMBERSHIP_TIERS.items())
    current_idx = next((i for i, (k, _) in enumerate(tiers_ordered) if k == tier_key), 0)
    next_tier_text = ""
    if current_idx < len(tiers_ordered) - 1:
        next_key, next_info = tiers_ordered[current_idx + 1]
        needed = next_info["min_spent"] - total_spent
        if needed > 0:
            next_tier_text = f"\n📈 Next tier: <b>{next_info['name']}</b> (spend ${needed:.2f} more)"

    discount_text = f" — {int(discount*100)}% discount" if discount > 0 else ""

    uname = f"@{user.get('username')}" if user.get("username") else "N/A"
    text = (
        f"👤 <b>Your Profile</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ Name: <b>{user.get('first_name') or 'N/A'}</b>\n"
        f"🔖 Username: <b>{uname}</b>\n"
        f"🆔 Telegram ID: <code>{user['telegram_id']}</code>\n"
        f"📅 Joined: <b>{joined}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Balance: <b>${user['balance']:.2f}</b>\n"
        f"👑 Membership: <b>{tier_name}</b>{discount_text}"
        f"{next_tier_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Total Orders: <b>{total_orders}</b>\n"
        f"💸 Total Spent: <b>${total_spent:.2f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 Referrals: <b>{referral_count}</b>\n"
        f"💵 Referral Earnings: <b>${referral_earnings:.2f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📎 <b>Your Referral Link:</b>\n"
        f"<code>{referral_link}</code>"
    )
    await callback.message.edit_text(text, reply_markup=profile_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "profile:orders")
async def cb_orders(callback: CallbackQuery, db_user: dict):
    orders = await get_user_orders(db_user["id"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="menu:profile"))

    if not orders:
        await callback.message.edit_text(
            "📋 <b>My Orders</b>\n\nYou haven't made any purchases yet.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    lines = []
    for o in orders[:15]:
        status_icon = {"completed": "✅", "refunded": "↩️", "pending": "⏳"}.get(o["status"], "❓")
        date = str(o.get("created_at", ""))[:10]
        lines.append(
            f"{status_icon} <b>#{o['id']}</b> — {o.get('product_name', 'N/A')} "
            f"(${o['total_price']:.2f}) <i>{date}</i>"
        )

    text = f"📋 <b>My Orders</b> ({len(orders)} total)\n\n" + "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "profile:referrals")
async def cb_referrals_list(callback: CallbackQuery, db_user: dict):
    referrals = await get_referrals(db_user["id"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="menu:profile"))

    if not referrals:
        await callback.message.edit_text(
            "🔗 <b>My Referrals</b>\n\nNo referrals yet. Share your link to start earning!",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    lines = []
    for r in referrals[:20]:
        name = r.get("first_name") or r.get("username") or "Friend"
        date = str(r.get("joined_at", ""))[:10]
        status = "✅ Bonus paid" if r.get("bonus_paid") else "⏳ Pending"
        lines.append(f"• <b>{name}</b> — {status} <i>({date})</i>")

    earnings = await get_referral_earnings(db_user["id"])
    text = (
        f"🔗 <b>My Referrals</b> ({len(referrals)} total)\n"
        f"💰 Total Earned: <b>${earnings:.2f}</b>\n\n"
        + "\n".join(lines)
    )
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()
