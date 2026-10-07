import os
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.keyboards.menus import main_menu_kb, admin_main_kb
from bot.config import BOT_NAME, ADMIN_IDS, MEMBERSHIP_TIERS
from bot.database import (
    get_user_total_spent, get_referrals, get_referral_earnings,
    get_custom_menu_buttons,
)
from bot.utils.ui import pe, DIVIDER, sky


async def build_main_kb():
    """Main menu keyboard including admin-defined custom buttons."""
    return main_menu_kb(await get_custom_menu_buttons())


def _webapp_kb() -> InlineKeyboardMarkup | None:
    """Returns a WebApp button if REPLIT_DEV_DOMAIN is set."""
    domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
    if not domain:
        return None
    url = f"https://{domain}/shop-miniapp/"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🌐 Open Web App", web_app=WebAppInfo(url=url)))
    return builder.as_markup()

router = Router()

BOT_TAGLINE = "Quality products at cheapest rates"


def _tier_label(tier: str) -> str:
    return MEMBERSHIP_TIERS.get(tier, MEMBERSHIP_TIERS["none"])["name"]


async def _build_welcome(message_or_user, db_user: dict, bot_username: str) -> str:
    """Build the full welcome / home card text."""
    tg = message_or_user
    first_name   = tg.first_name or "User"
    username     = f"@{tg.username}" if tg.username else "—"
    tg_id        = tg.id
    balance      = db_user["balance"]
    tier         = db_user.get("membership_type", "none")
    tier_label   = _tier_label(tier)
    total_spent  = await get_user_total_spent(db_user["id"])
    referrals    = await get_referrals(db_user["id"])
    ref_count    = len(referrals)
    ref_earnings = await get_referral_earnings(db_user["id"])
    ref_link     = f"https://t.me/{bot_username}?start={tg_id}"

    return (
        f"{pe('sparkles')} <b>{BOT_NAME.upper()}</b> {pe('crown')}\n"
        f"{DIVIDER}\n"
        f"👋 <b>Welcome back, {first_name}!</b>\n"
        f"<i>{BOT_TAGLINE}</i>\n\n"
        f"{DIVIDER}\n"
        f"🏷️ <b>Username:</b> {username}\n"
        f"🆔 <b>UserID:</b> <code>{tg_id}</code>\n"
        f"{pe('trophy')} <b>Membership:</b> {tier_label}\n"
        f"{pe('money')} <b>Balance:</b> ${balance:.2f}\n"
        f"{pe('diamond')} <b>Total Spent:</b> ${total_spent:.2f}\n"
        f"👥 <b>Referrals:</b> {ref_count}\n"
        f"💸 <b>Referral Earning:</b> ${ref_earnings:.2f}\n"
        f"{pe('link')} <b>Referral Link:</b> <a href=\"{ref_link}\">{ref_link}</a>\n"
        f"{DIVIDER}\n\n"
        f"Choose an option below to get started."
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: dict):
    bot_username = os.environ.get("BOT_USERNAME", "Paktools_bot")

    # Deep-link: /start prod_5  → open product #5 directly
    payload = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""
    if payload.startswith("prod_"):
        try:
            from bot.database import get_product
            from bot.database import get_membership_discount
            from bot.keyboards.menus import product_detail_kb
            import json as _json
            product_id = int(payload.split("_", 1)[1])
            product = await get_product(product_id)
            if product and product.get("is_active") and product.get("stock_count", 0) > 0:
                price = product.get("price", 0)
                is_free = price == 0.0
                discount = await get_membership_discount(db_user) if not is_free else 0.0
                final_price = round(price * (1 - discount), 2)
                try:
                    custom_btns = _json.loads(product.get("custom_buttons") or "[]")
                except Exception:
                    custom_btns = []
                from bot.database import has_product_alert
                alert_on = await has_product_alert(message.from_user.id, product_id)
                logo = product.get("logo") or "🏷️"
                warranty = product.get("warranty") or "No Warranty"
                product_type = product.get("product_type") or "Account"
                delivery_type = product.get("delivery_type") or "Manual"
                raw_desc = (product.get("description") or "").strip()
                desc_block = ""
                if raw_desc:
                    desc_lines = "\n".join(f"⚡ {l.strip()}" for l in raw_desc.splitlines() if l.strip())
                    desc_block = f"\n\n<b>📊 Product Description</b>\n{'━'*19}\n{desc_lines}"
                if is_free:
                    price_display = "<b>FREE 🎉</b>"
                else:
                    price_display = f"<b>${final_price:.2f}</b>"
                text = (
                    f"{logo} <b>{product['name']}</b>\n\n"
                    f"💰 Price: {price_display}\n"
                    f"📦 Stock:  <b>{product.get('stock_count', 0)}</b>\n"
                    f"🛡 Warranty:  <b>{warranty}</b>\n"
                    f"🏷 Product Type:  <b>{product_type}</b>\n"
                    f"🚚 Delivery Type:  <b>{delivery_type}</b>"
                    f"{desc_block}"
                )
                kb = product_detail_kb(product_id, qty=1, unit_price=final_price,
                                       is_free=is_free, has_alert=alert_on,
                                       custom_buttons=custom_btns)
                await message.answer(text, reply_markup=kb, parse_mode="HTML")
                return
        except Exception:
            pass  # fall through to normal start

    text = await _build_welcome(message.from_user, db_user, bot_username)
    await message.answer(text, reply_markup=await build_main_kb(), parse_mode="HTML",
                         disable_web_page_preview=True)


@router.message(Command("menu"))
async def cmd_menu(message: Message, db_user: dict):
    bot_username = os.environ.get("BOT_USERNAME", "")
    text = await _build_welcome(message.from_user, db_user, bot_username)
    await message.answer(text, reply_markup=await build_main_kb(), parse_mode="HTML",
                         disable_web_page_preview=True)


@router.message(Command("admin"))
async def cmd_admin(message: Message, db_user: dict):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ You don't have admin access.")
        return
    await message.answer(
        f"{pe('lock')} <b>ADMIN CONTROL PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Welcome back, Admin {pe('crown')}",
        reply_markup=admin_main_kb(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, db_user: dict):
    bot_username = os.environ.get("BOT_USERNAME", "")
    text = await _build_welcome(callback.from_user, db_user, bot_username)
    kb = await build_main_kb()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML",
                                         disable_web_page_preview=True)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.bot.send_message(callback.message.chat.id, text, reply_markup=kb,
                                        parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("menu:custom:"))
async def cb_custom_menu_button(callback: CallbackQuery):
    """Popup / message for an admin-defined custom main-menu button."""
    try:
        index = int(callback.data.split(":")[2])
        buttons = await get_custom_menu_buttons()
        button = buttons[index]
    except Exception:
        await callback.answer("Button not found.", show_alert=True)
        return
    value = button.get("value", "")
    if len(value) <= 190:
        await callback.answer(value or "—", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    builder.row(sky("🏠 Main Menu", callback_data="menu:main"))
    await callback.message.answer(
        f"<b>{button.get('label', 'Info')}</b>\n\n{value}",
        reply_markup=builder.as_markup(), parse_mode="HTML",
    )
    await callback.answer()
