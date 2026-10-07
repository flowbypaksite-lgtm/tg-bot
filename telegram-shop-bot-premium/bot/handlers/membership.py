from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from bot.database import get_user_total_spent
from bot.config import MEMBERSHIP_TIERS

router = Router()


@router.callback_query(F.data == "menu:membership")
async def cb_membership(callback: CallbackQuery, db_user: dict):
    tier_key = db_user.get("membership_type", "none")
    tier_info = MEMBERSHIP_TIERS.get(tier_key, MEMBERSHIP_TIERS["none"])
    tier_name = tier_info["name"]
    discount = tier_info["discount"]
    total_spent = await get_user_total_spent(db_user["id"])

    # Build tier progress display
    tiers_ordered = list(MEMBERSHIP_TIERS.items())
    tier_lines = []
    for key, info in tiers_ordered:
        is_current = key == tier_key
        marker = "▶️" if is_current else ("✅" if total_spent >= info["min_spent"] else "🔒")
        disc = f" — {int(info['discount']*100)}% off" if info["discount"] > 0 else ""
        req = f" (from ${info['min_spent']:.0f} spent)" if info["min_spent"] > 0 else " (default)"
        tier_lines.append(f"{marker} <b>{info['name']}</b>{disc}{req}")

    # Next tier
    current_idx = next((i for i, (k, _) in enumerate(tiers_ordered) if k == tier_key), 0)
    progress_text = ""
    if current_idx < len(tiers_ordered) - 1:
        next_key, next_info = tiers_ordered[current_idx + 1]
        needed = max(0, next_info["min_spent"] - total_spent)
        if needed > 0:
            progress_text = (
                f"\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 <b>Next tier:</b> {next_info['name']}\n"
                f"💸 Spend <b>${needed:.2f}</b> more to unlock it!"
            )
        else:
            progress_text = f"\n🏆 <b>Congratulations — you're at the highest tier!</b>"

    discount_line = f"🏷️ Your discount: <b>{int(discount*100)}%</b> on all products" if discount > 0 else "🏷️ No discount yet — start spending to unlock tiers!"

    text = (
        f"👑 <b>Membership Tiers</b>\n\n"
        f"Your tier: <b>{tier_name}</b>\n"
        f"Total spent: <b>${total_spent:.2f}</b>\n"
        f"{discount_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>All Tiers:</b>\n"
        + "\n".join(tier_lines)
        + progress_text
        + "\n\n<i>Tiers upgrade automatically as you purchase products!</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛍️ Go to Shop", callback_data="menu:shop"))
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()
