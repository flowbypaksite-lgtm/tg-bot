import html
import logging
import io
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from bot.keyboards.menus import (
    admin_main_kb, admin_products_kb, admin_product_manage_kb,
    admin_delete_confirm_kb, admin_user_detail_kb, cancel_kb,
    admin_redeem_codes_kb,
)
from bot.database import (
    get_stats, get_products, get_product, toggle_product, update_product,
    delete_product, add_product, add_stock_items, remove_stock_items,
    get_stock_items, get_all_users, get_all_orders, ban_user,
    update_balance, set_user_balance, get_user_by_id, search_users,
    get_all_pending_deposits, get_pending_deposit, approve_deposit, reject_deposit,
    get_setting, set_setting,
    create_redeem_code, get_all_redeem_codes, delete_redeem_code,
    get_product_alert_subscribers, get_user, create_order, claim_stock_item,
    complete_order, refund_order,
)
from bot.config import ADMIN_IDS
from bot.keyboards.menus import broadcast_buy_kb
from bot.utils.ui import DIVIDER, pe

router = Router()
logger = logging.getLogger(__name__)


def is_admin(tg_id: int) -> bool:
    return tg_id in ADMIN_IDS


async def _check_admin(callback: CallbackQuery) -> bool:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied.", show_alert=True)
        return False
    return True


class AdminStates(StatesGroup):
    adding_name = State()
    adding_desc = State()
    adding_price = State()
    editing_name = State()
    editing_desc = State()
    editing_price = State()
    adding_stock = State()
    removing_stock = State()
    adding_balance = State()
    deducting_balance = State()
    setting_balance = State()
    broadcast_msg = State()
    product_broadcast_select = State()
    product_broadcast_msg = State()
    searching_user = State()
    editing_sadapay = State()
    editing_trc20 = State()
    editing_bep20 = State()
    editing_binancepay = State()
    editing_referral_bonus = State()
    editing_low_stock_threshold = State()
    # Manual delivery
    manual_delivery_uid = State()
    manual_delivery_product = State()
    manual_delivery_data = State()
    # Logo editing
    editing_logo = State()
    editing_photo_logo = State()
    # Product extra fields
    editing_warranty = State()
    editing_ptype = State()
    editing_delivery = State()
    # Custom product buttons
    adding_blue_btn_label = State()
    adding_blue_btn_url = State()
    adding_green_btn_label = State()
    adding_green_btn_text = State()
    # Quick balance — step 1: enter user ID, step 2: enter amount
    quick_add_uid = State()
    quick_add_amount = State()
    quick_remove_uid = State()
    quick_remove_amount = State()
    # Redeem code creation
    redeem_create_code = State()
    redeem_create_amount = State()
    redeem_create_limit = State()
    redeem_create_expiry = State()


# ─── Main Panel ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:main")
async def cb_admin_main(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    await callback.message.edit_text(
        "🔐 <b>Admin Panel</b>\n\nWelcome, Admin! Choose an action:",
        reply_markup=admin_main_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Statistics ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    s = await get_stats()
    low_stock_threshold = await get_setting("low_stock_threshold")
    try:
        low_stock_threshold = int(low_stock_threshold)
    except (TypeError, ValueError):
        low_stock_threshold = 3
    text = (
        f"📊 <b>Bot Statistics</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users: <b>{s['users']}</b>\n"
        f"🆕 New Today: <b>{s['new_today']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Active Products: <b>{s['products']}</b>\n"
        f"🗃️ Available Stock: <b>{s['total_stock']}</b>\n"
        f"⚠️ Low-Stock Threshold: <b>{low_stock_threshold} units</b>\n"
        f"📋 Total Orders: <b>{s['orders']}</b>\n"
        f"💰 Total Revenue: <b>${s['revenue']:.2f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ Pending Deposits: <b>{s['pending_deposits']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Refresh", callback_data="admin:stats"))
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


# ─── Products ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:products")
async def cb_admin_products(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    products = await get_products(active_only=False)
    await callback.message.edit_text(
        f"📦 <b>Products</b> ({len(products)} total)\n\nTap a product to manage it:",
        reply_markup=admin_products_kb(products),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:prod:"))
async def cb_admin_prod_detail(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    p = await get_product(product_id)
    if not p:
        await callback.answer("Product not found.", show_alert=True)
        return
    stock = p.get("stock_count", 0)
    status = "✅ Active" if p.get("is_active") else "❌ Inactive"
    has_photo = bool(p.get("logo_file_id"))
    logo_line = f"\n🖼 Logo: <b>Photo set</b>" if has_photo else f"\n🔤 Logo: <b>{p.get('logo') or '🏷️'}</b>"
    text = (
        f"🏷️ <b>{p['name']}</b>\n\n"
        f"💵 Price: <b>${p['price']:.2f}</b>\n"
        f"📦 Stock: <b>{stock}</b>\n"
        f"Status: <b>{status}</b>"
        f"{logo_line}\n\n"
        f"📝 {p.get('description', 'No description.')}"
    )
    kb = admin_product_manage_kb(product_id, bool(p.get("is_active")), has_photo=has_photo)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.bot.send_message(callback.message.chat.id, text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:toggle:"))
async def cb_toggle_product(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    await toggle_product(product_id)
    await cb_admin_prod_detail(callback)


# ─── Add Product ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:add_product")
async def cb_add_product(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.adding_name)
    await callback.message.edit_text(
        "➕ <b>Add New Product</b>\n\n📝 Step 1/3: Send the product <b>name</b>:",
        reply_markup=cancel_kb("admin:products"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.adding_name)
async def process_adding_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminStates.adding_desc)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:products"))
    await message.answer(
        f"✅ Name: <b>{message.text.strip()}</b>\n\n📝 Step 2/3: Send the product <b>description</b>:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.adding_desc)
async def process_adding_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(desc=message.text.strip())
    await state.set_state(AdminStates.adding_price)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:products"))
    await message.answer(
        "📝 Step 3/3: Send the product <b>price</b> in USD (e.g. <code>9.99</code>):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.adding_price)
async def process_adding_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = round(float(message.text.strip().replace("$", "")), 2)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Invalid price. Enter a positive number like <code>9.99</code>.", parse_mode="HTML")
        return
    data = await state.get_data()
    await state.clear()
    product_id = await add_product(data["name"], data["desc"], price)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📦 Add Stock Now", callback_data=f"admin:add_stock:{product_id}"))
    builder.row(InlineKeyboardButton(text="◀️ Back to Products", callback_data="admin:products"))
    await message.answer(
        f"✅ <b>Product Added!</b>\n\n"
        f"Name: <b>{data['name']}</b>\n"
        f"Price: <b>${price:.2f}</b>\n\n"
        f"Now add stock (email:password) for this product:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


# ─── Edit Product ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:edit_name:"))
async def cb_edit_name(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.editing_name)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "✏️ <b>Edit Product Name</b>\n\nSend the new name:",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_name)
async def process_edit_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    await update_product(data["product_id"], name=message.text.strip())
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer(f"✅ Product name updated to: <b>{message.text.strip()}</b>", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:edit_desc:"))
async def cb_edit_desc(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.editing_desc)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "✏️ <b>Edit Description</b>\n\nSend the new description:",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_desc)
async def process_edit_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    await update_product(data["product_id"], description=message.text.strip())
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer("✅ Product description updated!", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:edit_price:"))
async def cb_edit_price(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.editing_price)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "💵 <b>Change Price</b>\n\nSend the new price (e.g. <code>9.99</code>):",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_price)
async def process_edit_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = round(float(message.text.strip().replace("$", "")), 2)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Invalid price. Enter a positive number like <code>9.99</code>.", parse_mode="HTML")
        return
    data = await state.get_data()
    await state.clear()
    await update_product(data["product_id"], price=price)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer(f"✅ Price updated to: <b>${price:.2f}</b>", reply_markup=builder.as_markup(), parse_mode="HTML")


# ─── Edit Logo ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:edit_logo:"))
async def cb_edit_logo(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.editing_logo)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "📝 <b>Set Logo Text / Emoji</b>\n\n"
        "Send any text to use as this product's logo — a regular emoji <b>or</b> a premium Telegram emoji.\n\n"
        "<b>For premium emoji:</b>\n"
        "1. Open <b>@RawDataBot</b> in Telegram\n"
        "2. Forward or send the premium emoji sticker/emoji to it\n"
        "3. Copy the <b>emoji text</b> from its reply\n"
        "4. Paste it here\n\n"
        "<b>Regular emoji examples:</b>\n"
        "🎬 🎨 💬 🤖 🎥 📧 💜 ⚡ 🔧 🌐\n\n"
        "<i>Whatever you send here appears next to the product name.</i>",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_logo)
async def process_edit_logo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    logo = (message.text or "").strip()
    if not logo:
        await message.answer("❌ Please send an emoji.", parse_mode="HTML")
        return
    data = await state.get_data()
    await state.clear()
    await update_product(data["product_id"], logo=logo)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer(
        f"✅ Logo updated to: <b>{logo}</b>\n\nThis logo now shows on all product buttons in the shop.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


# ─── Custom Product Buttons (Blue = URL, Green = Text popup) ─────────────────

import json as _json


def _parse_custom_buttons(product: dict) -> list:
    try:
        return _json.loads(product.get("custom_buttons") or "[]")
    except Exception:
        return []


async def _save_custom_buttons(product_id: int, btns: list):
    await update_product(product_id, custom_buttons=_json.dumps(btns, ensure_ascii=False))


@router.callback_query(F.data.startswith("admin:add_blue_btn:"))
async def cb_add_blue_btn(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback): return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.adding_blue_btn_label)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "🔵 <b>Add Blue Button (URL Link)</b>\n\n"
        "Step 1 — Send the <b>button label</b> (what users will see):\n"
        "<i>e.g. Watch Tutorial, Visit Website</i>",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.adding_blue_btn_label)
async def process_blue_btn_label(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(btn_label=message.text.strip())
    await state.set_state(AdminStates.adding_blue_btn_url)
    data = await state.get_data()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer(
        f"🔵 Label: <b>{message.text.strip()}</b>\n\n"
        f"Step 2 — Send the <b>URL</b> the button should open:\n"
        f"<i>e.g. https://youtube.com/...</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.adding_blue_btn_url)
async def process_blue_btn_url(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer("❌ URL must start with http:// or https://")
        return
    data = await state.get_data()
    await state.clear()
    product = await get_product(data["product_id"])
    btns = _parse_custom_buttons(product) if product else []
    btns.append({"label": data["btn_label"], "type": "url", "value": url})
    await _save_custom_buttons(data["product_id"], btns)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back to Product", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer(
        f"✅ <b>Blue Button Added</b>\n\n🔵 {data['btn_label']}\n🔗 {url}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:add_green_btn:"))
async def cb_add_green_btn(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback): return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.adding_green_btn_label)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "🟢 <b>Add Green Button (Text Info)</b>\n\n"
        "Step 1 — Send the <b>button label</b>:\n"
        "<i>e.g. Contact Support, How to Use</i>",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.adding_green_btn_label)
async def process_green_btn_label(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(btn_label=message.text.strip())
    await state.set_state(AdminStates.adding_green_btn_text)
    data = await state.get_data()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer(
        f"🟢 Label: <b>{message.text.strip()}</b>\n\n"
        f"Step 2 — Send the <b>text</b> shown when users tap this button:\n"
        f"<i>e.g. Contact @support for help with this product.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.adding_green_btn_text)
async def process_green_btn_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    await state.clear()
    product = await get_product(data["product_id"])
    btns = _parse_custom_buttons(product) if product else []
    btns.append({"label": data["btn_label"], "type": "text", "value": message.text.strip()})
    await _save_custom_buttons(data["product_id"], btns)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back to Product", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer(
        f"✅ <b>Green Button Added</b>\n\n🟢 {data['btn_label']}\n💬 {message.text.strip()}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:manage_btns:"))
async def cb_manage_btns(callback: CallbackQuery):
    if not await _check_admin(callback): return
    product_id = int(callback.data.split(":")[2])
    product = await get_product(product_id)
    btns = _parse_custom_buttons(product) if product else []
    builder = InlineKeyboardBuilder()
    if not btns:
        builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{product_id}"))
        await callback.message.edit_text(
            "🗂 <b>Custom Buttons</b>\n\nNo custom buttons added yet.\n"
            "Use 🔵 Add Blue Button or 🟢 Add Green Button.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    lines = []
    for i, btn in enumerate(btns):
        icon = "🔵" if btn.get("type") == "url" else "🟢"
        lines.append(f"{icon} <b>{btn['label']}</b>")
        builder.row(InlineKeyboardButton(
            text=f"🗑 Delete: {btn['label']}",
            callback_data=f"admin:del_btn:{product_id}:{i}",
        ))
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{product_id}"))
    await callback.message.edit_text(
        f"🗂 <b>Custom Buttons</b> ({len(btns)} total)\n\n" + "\n".join(lines) +
        "\n\nTap a button below to delete it:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:del_btn:"))
async def cb_del_btn(callback: CallbackQuery):
    if not await _check_admin(callback): return
    parts = callback.data.split(":")
    product_id = int(parts[2])
    btn_index = int(parts[3])
    product = await get_product(product_id)
    btns = _parse_custom_buttons(product) if product else []
    if 0 <= btn_index < len(btns):
        removed = btns.pop(btn_index)
        await _save_custom_buttons(product_id, btns)
        await callback.answer(f"🗑 Deleted: {removed['label']}", show_alert=False)
    else:
        await callback.answer("Button not found.", show_alert=True)
    await cb_manage_btns(callback)


# ─── Warranty / Product Type / Delivery Type ─────────────────────────────────

@router.callback_query(F.data.startswith("admin:edit_warranty:"))
async def cb_edit_warranty(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback): return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.editing_warranty)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "🛡 <b>Set Warranty</b>\n\n"
        "Send the warranty text, e.g.:\n"
        "<code>No Warranty</code>\n"
        "<code>1 Month</code>\n"
        "<code>3 Months</code>\n"
        "<code>Lifetime</code>",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_warranty)
async def process_edit_warranty(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    await state.clear()
    await update_product(data["product_id"], warranty=message.text.strip())
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer(f"✅ Warranty set to: <b>{message.text.strip()}</b>", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:edit_ptype:"))
async def cb_edit_ptype(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback): return
    product_id = int(callback.data.split(":")[2])
    builder = InlineKeyboardBuilder()
    for label in ["Account", "Coupon / Link", "Software Key", "Subscription", "Service"]:
        builder.row(InlineKeyboardButton(text=label, callback_data=f"admin:set_ptype:{product_id}:{label}"))
    builder.row(InlineKeyboardButton(text="✏️ Custom…", callback_data=f"admin:set_ptype_custom:{product_id}"))
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data=f"admin:prod:{product_id}"))
    await callback.message.edit_text(
        "🏷 <b>Set Product Type</b>\n\nChoose or enter custom:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:set_ptype:"))
async def cb_set_ptype(callback: CallbackQuery):
    if not await _check_admin(callback): return
    parts = callback.data.split(":", 3)
    product_id = int(parts[2])
    value = parts[3]
    await update_product(product_id, product_type=value)
    await callback.answer(f"✅ Product type: {value}", show_alert=False)
    await cb_admin_prod_detail(callback)


@router.callback_query(F.data.startswith("admin:set_ptype_custom:"))
async def cb_set_ptype_custom(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback): return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.editing_ptype)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "🏷 <b>Custom Product Type</b>\n\nSend the product type text:",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_ptype)
async def process_edit_ptype(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    await state.clear()
    await update_product(data["product_id"], product_type=message.text.strip())
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer(f"✅ Product type: <b>{message.text.strip()}</b>", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:edit_delivery:"))
async def cb_edit_delivery(callback: CallbackQuery):
    if not await _check_admin(callback): return
    product_id = int(callback.data.split(":")[2])
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🤖 Automatic", callback_data=f"admin:set_delivery:{product_id}:Automatic"),
        InlineKeyboardButton(text="👤 Manual",    callback_data=f"admin:set_delivery:{product_id}:Manual"),
    )
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data=f"admin:prod:{product_id}"))
    await callback.message.edit_text(
        "🚚 <b>Set Delivery Type</b>\n\nHow is this product delivered?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:set_delivery:"))
async def cb_set_delivery(callback: CallbackQuery):
    if not await _check_admin(callback): return
    parts = callback.data.split(":")
    product_id = int(parts[2])
    value = parts[3]
    await update_product(product_id, delivery_type=value)
    await callback.answer(f"✅ Delivery: {value}", show_alert=False)
    await cb_admin_prod_detail(callback)


# ─── Photo Logo Upload ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:upload_logo:"))
async def cb_upload_logo(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.editing_photo_logo)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "🖼 <b>Upload Product Logo</b>\n\n"
        "Send the product logo as a <b>Telegram Photo</b> (tap the 📎 paperclip and choose Photo/Video).\n\n"
        "⚠️ Send as a <b>photo</b>, not as a file/document.\n\n"
        "The highest-quality version will be saved automatically.",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_photo_logo)
async def process_photo_logo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.photo:
        await message.answer(
            "❌ Please send a <b>photo</b>, not a file or text.\n\n"
            "Tap the 📎 paperclip → Photo/Video.",
            parse_mode="HTML",
        )
        return
    # Telegram provides multiple sizes — last entry is always the highest quality
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    await state.clear()
    await update_product(data["product_id"], logo_file_id=file_id)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back to Product", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer_photo(
        photo=file_id,
        caption=(
            "✅ <b>Product logo saved!</b>\n\n"
            "This photo will now appear above the product info when users tap it in the shop.\n\n"
            "You can replace it anytime with <b>🖼 Change Product Logo</b>, "
            "or remove it with <b>🗑 Remove Product Logo</b>."
        ),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:set_status:"))
async def cb_set_status(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    parts = callback.data.split(":")
    product_id = int(parts[2])
    value = parts[3]  # "🟢", "🔴", or "auto"
    emoji = "" if value == "auto" else value   # "" → clears to NULL (auto mode)
    await update_product(product_id, status_emoji=emoji)
    label = {"🟢": "🟢 Green", "🔴": "🔴 Red", "": "🔄 Auto"}.get(emoji, emoji)
    await callback.answer(f"Status set to {label}!", show_alert=False)
    # Refresh the product manage screen
    await cb_admin_prod_detail(callback)


@router.callback_query(F.data.startswith("admin:remove_logo:"))
async def cb_remove_logo(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    await update_product(product_id, logo_file_id="")   # "" → clears to NULL
    p = await get_product(product_id)
    await callback.answer("🗑 Photo logo removed!", show_alert=False)
    # Re-render the product manage screen (no photo now)
    stock = p.get("stock_count", 0) if p else 0
    status = "✅ Active" if p and p.get("is_active") else "❌ Inactive"
    emoji = (p.get("logo") or "🏷️") if p else "🏷️"
    text = (
        f"🏷️ <b>{p['name'] if p else 'Product'}</b>\n\n"
        f"💵 Price: <b>${p['price']:.2f}</b>\n"
        f"📦 Stock: <b>{stock}</b>\n"
        f"Status: <b>{status}</b>\n"
        f"🔤 Logo: <b>{emoji}</b>\n\n"
        f"📝 {p.get('description', 'No description.') if p else ''}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_product_manage_kb(product_id, bool(p and p.get("is_active")), has_photo=False),
        parse_mode="HTML",
    )


# ─── Delete Product ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:delete_confirm:"))
async def cb_delete_confirm(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    p = await get_product(product_id)
    if not p:
        await callback.answer("Product not found.", show_alert=True)
        return
    await callback.message.edit_text(
        f"🗑️ <b>Delete Product?</b>\n\n<b>{p['name']}</b>\n\nThis will also delete all its stock. Are you sure?",
        reply_markup=admin_delete_confirm_kb(product_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:delete:"))
async def cb_delete_product(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    await delete_product(product_id)
    products = await get_products(active_only=False)
    await callback.message.edit_text(
        "✅ <b>Product deleted.</b>\n\nRemaining products:",
        reply_markup=admin_products_kb(products),
        parse_mode="HTML",
    )
    await callback.answer("🗑️ Deleted!")


# ─── Stock Management ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:add_stock:"))
async def cb_add_stock(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.adding_stock)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "➕ <b>Add Stock</b>\n\n"
        "Send accounts — one per line in format:\n"
        "<code>email@example.com:password</code>\n\n"
        "You can paste multiple lines at once.",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.adding_stock)
async def process_adding_stock(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()

    # Support .txt file upload (document)
    if message.document:
        doc = message.document
        mime = doc.mime_type or ""
        name = (doc.file_name or "").lower()
        if not (mime in ("text/plain", "application/octet-stream") or name.endswith(".txt")):
            await message.answer(
                "❌ Please send a <b>.txt</b> file (one account per line), or paste the accounts directly as text.",
                parse_mode="HTML",
            )
            return
        try:
            file = await message.bot.get_file(doc.file_id)
            buf = io.BytesIO()
            await message.bot.download_file(file.file_path, buf)
            raw_text = buf.getvalue().decode("utf-8", errors="replace")
        except Exception as e:
            await message.answer(f"❌ Failed to download file: <code>{e}</code>", parse_mode="HTML")
            return
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    else:
        lines = [l.strip() for l in (message.text or "").splitlines() if l.strip()]

    if not lines:
        await message.answer("❌ No accounts found. Send one account per line or attach a .txt file.")
        return

    await state.clear()
    result = await add_stock_items(data["product_id"], lines)
    # Fetch product after adding stock so stock_count reflects new total
    product = await get_product(data["product_id"])
    product_name = product["name"] if product else f"Product #{data['product_id']}"
    new_total = product["stock_count"] if product else result["added"]
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{data['product_id']}"))
    builder.row(InlineKeyboardButton(text="➕ Add More Stock", callback_data=f"admin:add_stock:{data['product_id']}"))

    if result["added"] == 0:
        header = (
            f"❌ <b>No Stock Added</b>\n\n"
            f"Product: <b>{html.escape(product_name)}</b>\n"
            f"No new stock was added — check the lines below for details\n"
            f"⚠️ Skipped (duplicate): <b>{result['skipped_duplicate']}</b>\n"
            f"❌ Skipped (invalid): <b>{result['skipped_invalid']}</b>\n"
            f"📦 Total available: <b>{new_total}</b>"
        )
    else:
        header = (
            f"✅ <b>Stock Updated</b>\n\n"
            f"Product: <b>{html.escape(product_name)}</b>\n"
            f"➕ Added: <b>{result['added']}</b>\n"
            f"⚠️ Skipped (duplicate): <b>{result['skipped_duplicate']}</b>\n"
            f"❌ Skipped (invalid): <b>{result['skipped_invalid']}</b>\n"
            f"📦 Total available: <b>{new_total}</b>"
        )
    lines_parts = [header]
    if result["invalid_lines"]:
        sample = "\n".join(f"<code>{html.escape(l)}</code>" for l in result["invalid_lines"][:5])
        extra = result["skipped_invalid"] - 5
        more = f"\n<i>…and {extra} more</i>" if extra > 0 else ""
        lines_parts.append(f"\n\n<b>Invalid lines</b> (need <code>value</code> or <code>left:right</code>):\n{sample}{more}")
    if result["duplicate_lines"]:
        sample = "\n".join(f"<code>{html.escape(l)}</code>" for l in result["duplicate_lines"][:5])
        extra = result["skipped_duplicate"] - 5
        more = f"\n<i>…and {extra} more</i>" if extra > 0 else ""
        lines_parts.append(f"\n\n<b>Duplicate lines</b> (already in stock):\n{sample}{more}")

    await message.answer(
        "".join(lines_parts),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:remove_stock:"))
async def cb_remove_stock(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.removing_stock)
    await state.update_data(product_id=product_id)
    await callback.message.edit_text(
        "➖ <b>Remove Stock</b>\n\nHow many items to remove? (Enter a number)",
        reply_markup=cancel_kb(f"admin:prod:{product_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.removing_stock)
async def process_removing_stock(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        count = int(message.text.strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Enter a valid positive number.")
        return
    data = await state.get_data()
    await state.clear()
    removed = await remove_stock_items(data["product_id"], count)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{data['product_id']}"))
    await message.answer(
        f"✅ Removed <b>{removed}</b> stock item(s).",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:view_stock:"))
async def cb_view_stock(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    product_id = int(callback.data.split(":")[2])
    items = await get_stock_items(product_id, used=False)
    p = await get_product(product_id)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:prod:{product_id}"))

    if not items:
        await callback.message.edit_text(
            f"📦 <b>{p['name'] if p else 'Product'}</b>\n\nNo stock available.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    lines = [f"<code>{i['account_data']}</code>" for i in items[:20]]
    more = f"\n<i>...and {len(items)-20} more</i>" if len(items) > 20 else ""
    await callback.message.edit_text(
        f"📦 <b>{p['name'] if p else 'Product'}</b> — {len(items)} in stock:\n\n"
        + "\n".join(lines) + more,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── /restock command — fast stock upload shortcut ───────────────────────────

async def _restock_add_lines(message: Message, product_id: int, lines: list[str]) -> None:
    """Validate, deduplicate, and add stock lines; reply with a detailed summary."""
    result = await add_stock_items(product_id, lines)
    product = await get_product(product_id)
    product_name = product["name"] if product else f"Product #{product_id}"
    new_total = product["stock_count"] if product else result["added"]
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back to Product", callback_data=f"admin:prod:{product_id}"))
    builder.row(InlineKeyboardButton(text="➕ Add More Stock", callback_data=f"admin:add_stock:{product_id}"))

    if result["added"] == 0:
        header = (
            f"❌ <b>No Stock Added</b>\n\n"
            f"Product: <b>{html.escape(product_name)}</b>\n"
            f"No new stock was added — check the lines below for details\n"
            f"⚠️ Skipped (duplicate): <b>{result['skipped_duplicate']}</b>\n"
            f"❌ Skipped (invalid): <b>{result['skipped_invalid']}</b>\n"
            f"📦 Total available: <b>{new_total}</b>"
        )
    else:
        header = (
            f"✅ <b>Stock Updated</b>\n\n"
            f"Product: <b>{html.escape(product_name)}</b>\n"
            f"➕ Added: <b>{result['added']}</b>\n"
            f"⚠️ Skipped (duplicate): <b>{result['skipped_duplicate']}</b>\n"
            f"❌ Skipped (invalid): <b>{result['skipped_invalid']}</b>\n"
            f"📦 Total available: <b>{new_total}</b>"
        )
    lines_parts = [header]
    if result["invalid_lines"]:
        sample = "\n".join(f"<code>{html.escape(l)}</code>" for l in result["invalid_lines"][:5])
        extra = result["skipped_invalid"] - 5
        more = f"\n<i>…and {extra} more</i>" if extra > 0 else ""
        lines_parts.append(f"\n\n<b>Invalid lines</b> (need <code>value</code> or <code>left:right</code>):\n{sample}{more}")
    if result["duplicate_lines"]:
        sample = "\n".join(f"<code>{html.escape(l)}</code>" for l in result["duplicate_lines"][:5])
        extra = result["skipped_duplicate"] - 5
        more = f"\n<i>…and {extra} more</i>" if extra > 0 else ""
        lines_parts.append(f"\n\n<b>Duplicate lines</b> (already in stock):\n{sample}{more}")

    await message.answer(
        "".join(lines_parts),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


def _parse_restock_id(text: str) -> tuple[int | None, str | None]:
    """Parse product ID from a /restock command string.

    Returns (product_id, error_message). product_id is None when the command
    has no argument; error_message is set when the argument is present but invalid.
    """
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None, None
    raw_id = parts[1].strip()
    if not raw_id.isdigit():
        return None, "❌ Product ID must be a number. Example: <code>/restock 2</code>"
    return int(raw_id), None


@router.message(Command("restock"))
async def cmd_restock(message: Message, state: FSMContext):
    """Quick restock command (text messages only).

    Usage:
      /restock               — shows product picker
      /restock <id>          — jumps directly to stock-entry for that product
    """
    if not is_admin(message.from_user.id):
        return

    product_id, err = _parse_restock_id(message.text or "")
    if err:
        await message.answer(err, parse_mode="HTML")
        return

    # ── /restock <id> → set FSM state, wait for stock ─────────────────────────
    if product_id is not None:
        p = await get_product(product_id)
        if not p:
            await message.answer(
                f"❌ No product found with ID <b>{product_id}</b>.",
                parse_mode="HTML",
            )
            return
        await state.set_state(AdminStates.adding_stock)
        await state.update_data(product_id=product_id)
        await message.answer(
            f"➕ <b>Add Stock — {p['name']}</b>\n\n"
            "Send accounts — one per line in format:\n"
            "<code>email@example.com:password</code>\n\n"
            "You can paste multiple lines at once, or send a <b>.txt</b> file.",
            reply_markup=cancel_kb(f"admin:prod:{product_id}"),
            parse_mode="HTML",
        )
        return

    # ── /restock (no ID) → show product picker ────────────────────────────────
    products = await get_products(active_only=False)
    if not products:
        await message.answer(
            "❌ No products exist yet. Create one from the Admin Panel first.",
            parse_mode="HTML",
        )
        return
    builder = InlineKeyboardBuilder()
    for p in products:
        stock = p.get("stock_count", 0)
        status = "🟢" if stock > 0 else "🔴"
        builder.button(
            text=f"{status} {p['name']} [{stock} in stock]",
            callback_data=f"admin:add_stock:{p['id']}",
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="◀️ Admin Panel", callback_data="admin:main"))
    await message.answer(
        "📦 <b>Quick Restock</b>\n\n"
        "Select a product to add stock to:\n"
        "<i>🔴 = out of stock  •  🟢 = has stock</i>\n\n"
        "<i>Tip: use <code>/restock &lt;id&gt;</code> to jump directly to a product.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(F.document, F.caption.startswith("/restock"))
async def cmd_restock_document(message: Message):
    """One-shot restock: send a .txt file with caption `/restock <id>`.

    Telegram puts the caption in message.caption (not message.text) for
    document messages, so this is a dedicated handler for that case.
    """
    if not is_admin(message.from_user.id):
        return

    product_id, err = _parse_restock_id(message.caption or "")
    if err:
        await message.answer(err, parse_mode="HTML")
        return
    if product_id is None:
        await message.answer(
            "❌ Include a product ID in the caption. Example: <code>/restock 2</code>",
            parse_mode="HTML",
        )
        return

    p = await get_product(product_id)
    if not p:
        await message.answer(
            f"❌ No product found with ID <b>{product_id}</b>.",
            parse_mode="HTML",
        )
        return

    doc = message.document
    mime = doc.mime_type or ""
    name = (doc.file_name or "").lower()
    if not (mime in ("text/plain", "application/octet-stream") or name.endswith(".txt")):
        await message.answer(
            "❌ Please attach a <b>.txt</b> file (one account per line).",
            parse_mode="HTML",
        )
        return

    try:
        file = await message.bot.get_file(doc.file_id)
        buf = io.BytesIO()
        await message.bot.download_file(file.file_path, buf)
        raw_text = buf.getvalue().decode("utf-8", errors="replace")
    except Exception as e:
        await message.answer(f"❌ Failed to download file: <code>{e}</code>", parse_mode="HTML")
        return

    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    if not lines:
        await message.answer("❌ The file appears to be empty.")
        return

    await _restock_add_lines(message, product_id, lines)


# ─── User Management ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:search_user")
async def cb_search_user(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.searching_user)
    await callback.message.edit_text(
        "🔍 <b>Search User</b>\n\n"
        "Send the user's <b>Telegram ID</b>, <b>@username</b>, or <b>name</b>:",
        reply_markup=cancel_kb("admin:main"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.searching_user)
async def process_search_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    query = message.text.strip().lstrip("@")
    users = await search_users(query)

    if not users:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔍 Search Again", callback_data="admin:search_user"))
        builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))
        await message.answer("❌ No users found.", reply_markup=builder.as_markup())
        return

    builder = InlineKeyboardBuilder()
    for u in users[:10]:
        name = u.get("first_name") or u.get("username") or f"User#{u['id']}"
        ban_icon = "🚫" if u.get("is_banned") else "✅"
        builder.button(
            text=f"{ban_icon} {name} (${u['balance']:.2f})",
            callback_data=f"admin:user:{u['id']}",
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))
    await message.answer(
        f"🔍 Found <b>{len(users)}</b> result(s):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


# ─── Quick Add / Remove Balance ───────────────────────────────────────────────

@router.callback_query(F.data == "admin:quick_add")
async def cb_quick_add(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.quick_add_uid)
    await state.update_data(action="add")
    await callback.message.edit_text(
        "💰 <b>Add Balance</b>\n\n"
        "Enter the user's <b>Telegram ID</b>:",
        reply_markup=cancel_kb("admin:main"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:quick_remove")
async def cb_quick_remove(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.quick_remove_uid)
    await state.update_data(action="remove")
    await callback.message.edit_text(
        "➖ <b>Remove Balance</b>\n\n"
        "Enter the user's <b>Telegram ID</b>:",
        reply_markup=cancel_kb("admin:main"),
        parse_mode="HTML",
    )
    await callback.answer()


async def _resolve_uid_step(message: Message, state: FSMContext, next_state: str, action_label: str):
    """Shared step: resolve telegram_id → ask for amount."""
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Telegram ID must be a number. Try again:")
        return
    tg_id = int(text)
    user = await get_user_by_id.__wrapped__(tg_id) if False else None
    # search by telegram_id directly
    from bot.database import get_user as _get_user
    user = await _get_user(tg_id)
    if not user:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))
        await message.answer(
            f"❌ No user found with Telegram ID <code>{tg_id}</code>.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await state.clear()
        return
    name = user.get("first_name") or user.get("username") or f"User#{user['id']}"
    await state.update_data(target_user_id=user["id"], target_name=name, target_tg_id=tg_id)
    await state.set_state(next_state)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:main"))
    await message.answer(
        f"👤 <b>{name}</b> (ID: <code>{tg_id}</code>)\n"
        f"💵 Current balance: <b>${user['balance']:.2f}</b>\n\n"
        f"Enter the amount to <b>{action_label}</b> (e.g. <code>10</code>):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.quick_add_uid)
async def process_quick_add_uid(message: Message, state: FSMContext):
    await _resolve_uid_step(message, state, AdminStates.quick_add_amount, "add")


@router.message(AdminStates.quick_remove_uid)
async def process_quick_remove_uid(message: Message, state: FSMContext):
    await _resolve_uid_step(message, state, AdminStates.quick_remove_amount, "remove")


@router.message(AdminStates.quick_add_amount)
async def process_quick_add_amount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = round(float(message.text.strip().replace("$", "")), 2)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Enter a valid positive number.")
        return
    data = await state.get_data()
    await state.clear()
    uid = data["target_user_id"]
    name = data["target_name"]
    await update_balance(uid, amount, "admin_credit", f"Admin added ${amount:.2f}")
    # Notify the user
    try:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="💰 View Wallet", callback_data="menu:wallet"))
        await message.bot.send_message(
            data["target_tg_id"],
            f"💰 <b>Balance Added!</b>\n\n"
            f"An admin has added <b>${amount:.2f}</b> to your wallet.\n"
            f"Check your balance in the Wallet section.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    except Exception:
        pass
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back to Admin", callback_data="admin:main"))
    await message.answer(
        f"✅ <b>Done!</b>\n\n"
        f"Added <b>${amount:.2f}</b> to <b>{name}</b>.\n"
        f"User has been notified.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.quick_remove_amount)
async def process_quick_remove_amount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = round(float(message.text.strip().replace("$", "")), 2)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Enter a valid positive number.")
        return
    data = await state.get_data()
    await state.clear()
    uid = data["target_user_id"]
    name = data["target_name"]
    await update_balance(uid, -amount, "admin_deduct", f"Admin removed ${amount:.2f}")
    # Notify the user
    try:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="💰 View Wallet", callback_data="menu:wallet"))
        await message.bot.send_message(
            data["target_tg_id"],
            f"⚠️ <b>Balance Adjusted</b>\n\n"
            f"An admin has removed <b>${amount:.2f}</b> from your wallet.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    except Exception:
        pass
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back to Admin", callback_data="admin:main"))
    await message.answer(
        f"✅ <b>Done!</b>\n\n"
        f"Removed <b>${amount:.2f}</b> from <b>{name}</b>.\n"
        f"User has been notified.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:user:"))
async def cb_admin_user(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    user_id = int(callback.data.split(":")[2])
    u = await get_user_by_id(user_id)
    if not u:
        await callback.answer("User not found.", show_alert=True)
        return
    name = u.get("first_name") or "N/A"
    uname = f"@{u['username']}" if u.get("username") else "no username"
    ban_status = "🚫 BANNED" if u.get("is_banned") else "✅ Active"
    from bot.config import MEMBERSHIP_TIERS
    tier = MEMBERSHIP_TIERS.get(u.get("membership_type", "none"), {}).get("name", "Free")
    text = (
        f"👤 <b>User Detail</b>\n\n"
        f"Name: <b>{name}</b>\n"
        f"Username: <b>{uname}</b>\n"
        f"Telegram ID: <code>{u['telegram_id']}</code>\n"
        f"Status: <b>{ban_status}</b>\n"
        f"Balance: <b>${u['balance']:.2f}</b>\n"
        f"Tier: <b>{tier}</b>\n"
        f"Joined: <b>{str(u.get('joined_at',''))[:10]}</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_user_detail_kb(user_id, bool(u.get("is_banned"))),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:ban:"))
async def cb_ban_user(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    user_id = int(callback.data.split(":")[2])
    u = await get_user_by_id(user_id)
    if not u:
        await callback.answer("User not found.", show_alert=True)
        return
    new_ban = not bool(u.get("is_banned"))
    await ban_user(user_id, new_ban)
    status = "🚫 Banned" if new_ban else "✅ Unbanned"
    await callback.answer(f"{status}!")
    # Refresh
    callback.data = f"admin:user:{user_id}"
    await cb_admin_user(callback)


@router.callback_query(F.data.startswith("admin:addbal:"))
async def cb_addbal(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    user_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.adding_balance)
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text(
        "➕ <b>Add Balance</b>\n\nHow much to add? (e.g. <code>10</code>):",
        reply_markup=cancel_kb(f"admin:user:{user_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.adding_balance)
async def process_add_balance(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = round(float(message.text.strip().replace("$", "")), 2)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Enter a valid positive number.")
        return
    data = await state.get_data()
    await state.clear()
    uid = data["target_user_id"]
    await update_balance(uid, amount, "admin_credit", f"Admin credited ${amount:.2f}")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:user:{uid}"))
    await message.answer(f"✅ Added <b>${amount:.2f}</b> to user.", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:deductbal:"))
async def cb_deductbal(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    user_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.deducting_balance)
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text(
        "➖ <b>Deduct Balance</b>\n\nHow much to deduct? (e.g. <code>5</code>):",
        reply_markup=cancel_kb(f"admin:user:{user_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.deducting_balance)
async def process_deduct_balance(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = round(float(message.text.strip().replace("$", "")), 2)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Enter a valid positive number.")
        return
    data = await state.get_data()
    await state.clear()
    uid = data["target_user_id"]
    await update_balance(uid, -amount, "admin_deduct", f"Admin deducted ${amount:.2f}")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:user:{uid}"))
    await message.answer(f"✅ Deducted <b>${amount:.2f}</b> from user.", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:setbal:"))
async def cb_setbal(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    user_id = int(callback.data.split(":")[2])
    await state.set_state(AdminStates.setting_balance)
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text(
        "💳 <b>Set Balance</b>\n\nEnter the exact new balance (e.g. <code>50.00</code>):",
        reply_markup=cancel_kb(f"admin:user:{user_id}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.setting_balance)
async def process_set_balance(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        balance = round(float(message.text.strip().replace("$", "")), 2)
        if balance < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Enter a valid non-negative number.")
        return
    data = await state.get_data()
    await state.clear()
    uid = data["target_user_id"]
    await set_user_balance(uid, balance)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"admin:user:{uid}"))
    await message.answer(f"✅ Balance set to <b>${balance:.2f}</b>.", reply_markup=builder.as_markup(), parse_mode="HTML")


# ─── Orders ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:orders")
async def cb_admin_orders(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    orders = await get_all_orders(limit=20)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))

    if not orders:
        await callback.message.edit_text("📋 <b>Orders</b>\n\nNo orders yet.", reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        return

    lines = []
    for o in orders:
        status_icon = {"completed": "✅", "refunded": "↩️", "pending": "⏳"}.get(o["status"], "❓")
        first = o.get("first_name") or "User"
        uname = f" @{o['username']}" if o.get("username") else f" [{o.get('telegram_id', o['user_id'])}]"
        date = str(o.get("created_at", ""))[:10]
        lines.append(f"{status_icon} <b>#{o['id']}</b> {first}{uname} — {o.get('product_name','?')} ${o['total_price']:.2f} <i>{date}</i>")

    await callback.message.edit_text(
        f"📋 <b>Recent Orders</b> ({len(orders)} shown)\n\n" + "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Pending Deposits ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:deposits")
async def cb_admin_deposits(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    deposits = await get_all_pending_deposits()
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Refresh", callback_data="admin:deposits"))
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))

    if not deposits:
        await callback.message.edit_text(
            "💳 <b>Pending Deposits</b>\n\nNo pending deposits! ✅",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    METHOD_NAMES = {"sadapay": "SadaPay", "trc20": "TRC20", "bep20": "BEP20"}
    lines = []
    for d in deposits:
        name = d.get("first_name") or d.get("username") or f"User#{d['user_id']}"
        method = METHOD_NAMES.get(d["method"], d["method"])
        date = str(d.get("created_at", ""))[:10]
        lines.append(
            f"• <b>#{d['id']}</b> {name} — ${d['amount']:.2f} via {method} <i>{date}</i>\n"
            f"  → /approve_{d['id']} to review"
        )

    await callback.message.edit_text(
        f"💳 <b>Pending Deposits</b> ({len(deposits)})\n\n" + "\n\n".join(lines) +
        "\n\n<i>Screenshots were sent to you when each deposit was submitted. Use the Approve/Reject buttons there.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:approve_dep:"))
async def cb_approve_deposit(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    deposit_id = int(callback.data.split(":")[2])
    dep = await approve_deposit(deposit_id)
    if not dep:
        await callback.answer("❌ Deposit not found or already processed.", show_alert=True)
        return

    METHOD_NAMES = {"sadapay": "💳 SadaPay", "trc20": "₿ TRC20", "bep20": "₿ BEP20"}
    method_name = METHOD_NAMES.get(dep["method"], dep["method"])

    # ── Auto-deliver checkout order if deposit is linked to a product ────────
    checkout_product_id = dep.get("checkout_product_id")
    checkout_qty = dep.get("checkout_qty") or 1
    order_result = None
    stock_missing = False  # set True when stock was deleted mid-session
    if checkout_product_id:
        try:
            product = await get_product(checkout_product_id)
            user_row = await get_user(dep["telegram_id"])
            if product and user_row:
                order_id = await create_order(user_row["id"], checkout_product_id, dep["amount"])
                stock = await claim_stock_item(checkout_product_id, user_row["id"], order_id)
                if stock:
                    await complete_order(order_id)
                    order_result = {
                        "product_name": product["name"],
                        "qty": checkout_qty,
                        "stock": stock,
                    }
                else:
                    # Stock was deleted mid-session — refund immediately and
                    # do NOT set order_result so no sales notification fires.
                    await refund_order(order_id, user_row["id"], dep["amount"])
                    stock_missing = True
                    stock_missing_product = product["name"]
        except Exception as e:
            logger.warning(f"Auto-deliver failed for checkout deposit #{deposit_id}: {e}")

    # Notify user
    try:
        builder = InlineKeyboardBuilder()
        if stock_missing:
            user_msg = (
                f"❌ <b>Out of Stock — Order Refunded</b>\n\n"
                f"📦 Product: <b>{stock_missing_product}</b>\n"
                f"💵 Amount: <b>${dep['amount']:.2f}</b> refunded to your balance.\n\n"
                f"The item you ordered became unavailable after your payment was received. "
                f"Your balance has been restored. Please choose another product or contact support."
            )
            builder.row(InlineKeyboardButton(text="🛍️ Shop Again", callback_data="menu:shop"))
            builder.row(InlineKeyboardButton(text="🆘 Support", callback_data="menu:support"))
        elif order_result:
            user_msg = (
                f"✅ <b>Order Delivered!</b>\n\n"
                f"📦 Product: <b>{order_result['product_name']}</b>\n"
                f"💵 Paid: <b>${dep['amount']:.2f}</b> via {method_name}\n\n"
                f"🎉 Here is your item:\n"
                f"<code>{order_result['stock']}</code>"
            )
            builder.row(InlineKeyboardButton(text="🛍️ Shop More", callback_data="menu:shop"))
        else:
            user_msg = (
                f"✅ <b>Deposit Approved!</b>\n\n"
                f"Amount: <b>${dep['amount']:.2f}</b>\n"
                f"Method: <b>{method_name}</b>\n"
                f"Reference: <b>#{deposit_id}</b>\n\n"
                f"Your balance has been updated. Happy shopping! 🛍️"
            )
            builder.row(InlineKeyboardButton(text="💰 View Wallet", callback_data="menu:wallet"))
        await callback.bot.send_message(dep["telegram_id"], user_msg, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Could not notify user of approved deposit: {e}")

    # ── Sales group notification — only fires for successfully delivered orders ─
    if order_result:
        try:
            from bot.config import SALES_GROUP_ID, BOT_USERNAME
            product_name = order_result["product_name"]
            qty = order_result["qty"]
            tg_user = await callback.bot.get_chat(dep["telegram_id"])
            raw_name = getattr(tg_user, "username", None) or getattr(tg_user, "first_name", None) or "User"
            masked = raw_name[0].upper() + "*" * max(4, len(raw_name) - 1)
            qty_str = f"{qty}×" if qty > 1 else "1×"
            group_text = f"🔥 User <b>{masked}</b> just bought {qty_str} <b>{product_name}</b>!"
            deep_link = f"https://t.me/{BOT_USERNAME}?start=prod_{dep.get('checkout_product_id')}"
            from aiogram.utils.keyboard import InlineKeyboardBuilder as _IKB
            from aiogram.types import InlineKeyboardButton as _IKBt
            gkb = _IKB()
            gkb.row(_IKBt(text=f"🛒 Get {product_name}", url=deep_link))
            await callback.bot.send_message(SALES_GROUP_ID, group_text,
                                            reply_markup=gkb.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not send group sale notification (deposit): {e}")

    # Update the admin message
    try:
        await callback.message.edit_caption(
            callback.message.caption + f"\n\n✅ <b>APPROVED</b> by admin",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer(f"✅ Deposit #{deposit_id} approved — ${dep['amount']:.2f} added!", show_alert=True)


@router.callback_query(F.data.startswith("admin:reject_dep:"))
async def cb_reject_deposit(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    deposit_id = int(callback.data.split(":")[2])
    dep = await reject_deposit(deposit_id)
    if not dep:
        await callback.answer("❌ Deposit not found or already processed.", show_alert=True)
        return

    # Notify user
    try:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="➕ Try Again", callback_data="wallet:deposit"))
        await callback.bot.send_message(
            dep["telegram_id"],
            f"❌ <b>Deposit Rejected</b>\n\n"
            f"Amount: <b>${dep['amount']:.2f}</b>\n"
            f"Reference: <b>#{deposit_id}</b>\n\n"
            f"Your deposit was not approved. If you believe this is an error, please contact support.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Could not notify user of rejected deposit: {e}")

    try:
        await callback.message.edit_caption(
            callback.message.caption + f"\n\n❌ <b>REJECTED</b> by admin",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer(f"❌ Deposit #{deposit_id} rejected.", show_alert=True)


# ─── Payment Settings ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:payment_settings")
async def cb_payment_settings(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    sadapay = await get_setting("sadapay_number")
    binancepay = await get_setting("binance_pay_id")
    trc20 = await get_setting("binance_trc20")
    bep20 = await get_setting("binance_bep20")

    text = (
        f"⚙️ <b>Payment Settings</b>\n\n"
        f"💳 <b>SadaPay Number:</b>\n<code>{sadapay}</code>\n\n"
        f"💛 <b>Binance Pay ID:</b>\n<code>{binancepay}</code>\n\n"
        f"₿ <b>Binance TRC20 (USDT):</b>\n<code>{trc20}</code>\n\n"
        f"₿ <b>Binance BEP20 (USDT):</b>\n<code>{bep20}</code>\n\n"
        f"Tap a button to update:"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Edit SadaPay Number", callback_data="admin:edit_sadapay"))
    builder.row(InlineKeyboardButton(text="Edit Binance Pay ID", callback_data="admin:edit_binancepay"))
    builder.row(InlineKeyboardButton(text="Edit Binance TRC20 Address", callback_data="admin:edit_trc20"))
    builder.row(InlineKeyboardButton(text="Edit Binance BEP20 Address", callback_data="admin:edit_bep20"))
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:edit_sadapay")
async def cb_edit_sadapay(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.editing_sadapay)
    await callback.message.edit_text(
        "💳 <b>Update SadaPay Number</b>\n\nSend the new SadaPay phone number:",
        reply_markup=cancel_kb("admin:payment_settings"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_sadapay)
async def process_edit_sadapay(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    val = message.text.strip()
    await set_setting("sadapay_number", val)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:payment_settings"))
    await message.answer(f"✅ SadaPay number updated to:\n<code>{val}</code>", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "admin:edit_binancepay")
async def cb_edit_binancepay(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.editing_binancepay)
    await callback.message.edit_text(
        "💛 <b>Update Binance Pay ID</b>\n\nSend the new Binance Pay ID:",
        reply_markup=cancel_kb("admin:payment_settings"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_binancepay)
async def process_edit_binancepay(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    val = message.text.strip()
    await set_setting("binance_pay_id", val)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:payment_settings"))
    await message.answer(f"✅ Binance Pay ID updated to:\n<code>{val}</code>", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "admin:edit_trc20")
async def cb_edit_trc20(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.editing_trc20)
    await callback.message.edit_text(
        "₿ <b>Update TRC20 Address</b>\n\nSend the new USDT TRC20 wallet address:",
        reply_markup=cancel_kb("admin:payment_settings"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_trc20)
async def process_edit_trc20(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    val = message.text.strip()
    await set_setting("binance_trc20", val)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:payment_settings"))
    await message.answer(f"✅ TRC20 address updated to:\n<code>{val}</code>", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "admin:edit_bep20")
async def cb_edit_bep20(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.editing_bep20)
    await callback.message.edit_text(
        "₿ <b>Update BEP20 Address</b>\n\nSend the new USDT BEP20 wallet address:",
        reply_markup=cancel_kb("admin:payment_settings"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_bep20)
async def process_edit_bep20(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    val = message.text.strip()
    await set_setting("binance_bep20", val)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:payment_settings"))
    await message.answer(f"✅ BEP20 address updated to:\n<code>{val}</code>", reply_markup=builder.as_markup(), parse_mode="HTML")


# ─── Manual Delivery ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:manual_delivery")
async def cb_manual_delivery(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.manual_delivery_uid)
    await callback.message.edit_text(
        "📦 <b>Manual Delivery</b>\n\n"
        "Step 1/3 — Enter the recipient's <b>Telegram ID</b>:",
        reply_markup=cancel_kb("admin:main"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.manual_delivery_uid)
async def process_manual_delivery_uid(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip().lstrip("@")
    from bot.database import get_user as _get_user
    user = None
    tg_id = None

    if text.isdigit():
        tg_id = int(text)
        user = await _get_user(tg_id)
    else:
        # Search by username
        results = await search_users(text)
        user = next((u for u in results if (u.get("username") or "").lower() == text.lower()), None)
        if user:
            tg_id = user["telegram_id"]

    if not user:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))
        await message.answer(
            f"❌ No user found for <code>{message.text.strip()}</code>.\n"
            f"The user must have started the bot at least once.\n\n"
            f"Try their <b>Telegram ID</b> or <b>@username</b> (without @).",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await state.clear()
        return
    name = user.get("first_name") or user.get("username") or f"User#{user['id']}"
    await state.update_data(target_tg_id=tg_id, target_name=name)
    await state.set_state(AdminStates.manual_delivery_product)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:main"))
    await message.answer(
        f"✅ Recipient: <b>{name}</b> (<code>{tg_id}</code>)\n\n"
        f"Step 2/3 — Enter the <b>product name</b> to show in the delivery message\n"
        f"(e.g. <code>CapCut Pro</code>):",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.manual_delivery_product)
async def process_manual_delivery_product(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    product_name = message.text.strip()
    await state.update_data(product_name=product_name)
    await state.set_state(AdminStates.manual_delivery_data)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:main"))
    await message.answer(
        f"✅ Product: <b>{product_name}</b>\n\n"
        f"Step 3/3 — Paste the <b>account credentials</b> to deliver:\n\n"
        f"<i>You can paste multiple lines — each line will be shown as-is.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.manual_delivery_data)
async def process_manual_delivery_data(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    credentials = message.text.strip()
    data = await state.get_data()
    await state.clear()
    tg_id = data["target_tg_id"]
    name = data["target_name"]
    product_name = data["product_name"]

    try:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🆘 Support", callback_data="menu:support"))
        builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))
        await message.bot.send_message(
            tg_id,
            f"📦 <b>Your Order is Ready!</b>\n\n"
            f"Product: <b>{product_name}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 <b>Account Credentials:</b>\n\n"
            f"<code>{credentials}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Please save these credentials. Contact support if you have any issues.</i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        result = "✅"
        result_text = f"Delivery sent to <b>{name}</b> (<code>{tg_id}</code>) successfully!"
    except Exception as e:
        result = "❌"
        result_text = f"Failed to deliver to <b>{name}</b> (<code>{tg_id}</code>).\nError: <code>{e}</code>"

    back_builder = InlineKeyboardBuilder()
    back_builder.row(InlineKeyboardButton(text="📦 Send Another", callback_data="admin:manual_delivery"))
    back_builder.row(InlineKeyboardButton(text="◀️ Admin Panel", callback_data="admin:main"))
    await message.answer(
        f"{result} <b>Manual Delivery</b>\n\n{result_text}",
        reply_markup=back_builder.as_markup(),
        parse_mode="HTML",
    )


# ─── Referral Settings ───────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:referral_settings")
async def cb_referral_settings(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    current = await get_setting("referral_bonus")
    try:
        amount = float(current)
    except (TypeError, ValueError):
        amount = 0.05
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Change Bonus Amount", callback_data="admin:edit_referral_bonus"))
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))
    await callback.message.edit_text(
        f"🔗 <b>Referral Settings</b>\n\n"
        f"Current referral bonus: <b>${amount:.2f}</b>\n\n"
        f"This amount is credited to the referrer when their invited user makes their first purchase.\n\n"
        f"Tap the button below to change it:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:edit_referral_bonus")
async def cb_edit_referral_bonus(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.editing_referral_bonus)
    await callback.message.edit_text(
        "✏️ <b>Set Referral Bonus</b>\n\n"
        "Enter the new referral bonus amount in USD\n"
        "(e.g. <code>0.05</code>, <code>1.00</code>, <code>5.00</code>):",
        reply_markup=cancel_kb("admin:referral_settings"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_referral_bonus)
async def process_edit_referral_bonus(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = round(float(message.text.strip().replace("$", "")), 4)
        if amount < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Enter a valid non-negative number (e.g. <code>0.05</code>).", parse_mode="HTML")
        return
    await state.clear()
    await set_setting("referral_bonus", str(amount))
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back to Referral Settings", callback_data="admin:referral_settings"))
    await message.answer(
        f"✅ Referral bonus updated to <b>${amount:.2f}</b>.\n\n"
        f"All future referral payouts will use this amount.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


# ─── Redeem Code Management ───────────────────────────────────────────────────

@router.callback_query(F.data == "admin:redeem_codes")
async def cb_admin_redeem_codes(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    codes = await get_all_redeem_codes()
    total = len(codes)
    active = sum(1 for c in codes if c["times_used"] < c["usage_limit"])
    text = (
        f"🎁 <b>Redeem Codes</b>\n\n"
        f"Total: <b>{total}</b> codes  •  Active: <b>{active}</b>\n\n"
        f"Tap a code to <b>delete</b> it, or create a new one:"
    )
    await callback.message.edit_text(text, reply_markup=admin_redeem_codes_kb(codes), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:redeem_create")
async def cb_redeem_create_start(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.redeem_create_code)
    await callback.message.edit_text(
        "🎁 <b>Create Redeem Code</b>\n\n"
        "Step 1/4 — Enter the <b>code text</b>:\n\n"
        "<i>Example: <code>WELCOME100</code>, <code>PROMO20</code></i>",
        reply_markup=cancel_kb("admin:redeem_codes"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.redeem_create_code)
async def process_redeem_code_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    code = message.text.strip().upper()
    if not code or len(code) > 30:
        await message.answer("❌ Code must be 1–30 characters. Try again:")
        return
    await state.update_data(new_code=code)
    await state.set_state(AdminStates.redeem_create_amount)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:redeem_codes"))
    await message.answer(
        f"✅ Code: <code>{code}</code>\n\n"
        f"Step 2/4 — Enter the <b>dollar amount</b> this code grants:\n"
        f"<i>Example: <code>100</code>, <code>50</code>, <code>20.50</code></i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.redeem_create_amount)
async def process_redeem_code_amount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = round(float(message.text.strip().replace("$", "")), 2)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Enter a valid positive number (e.g. <code>50</code>).", parse_mode="HTML")
        return
    await state.update_data(new_amount=amount)
    await state.set_state(AdminStates.redeem_create_limit)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:redeem_codes"))
    await message.answer(
        f"✅ Amount: <b>${amount:.2f}</b>\n\n"
        f"Step 3/4 — Enter the <b>usage limit</b> (how many times can this code be used):\n"
        f"<i>Example: <code>1</code> for single-use, <code>100</code> for 100 uses</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.redeem_create_limit)
async def process_redeem_code_limit(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await message.answer("❌ Enter a whole number ≥ 1 (e.g. <code>1</code>).", parse_mode="HTML")
        return
    await state.update_data(new_limit=int(text))
    await state.set_state(AdminStates.redeem_create_expiry)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⏩ No Expiry", callback_data="admin:redeem_no_expiry"))
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:redeem_codes"))
    await message.answer(
        f"✅ Usage limit: <b>{text}</b>\n\n"
        f"Step 4/4 — Enter an <b>expiry date</b> (optional):\n"
        f"<i>Format: <code>YYYY-MM-DD</code> (e.g. <code>2025-12-31</code>)\n"
        f"Or tap No Expiry to skip.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:redeem_no_expiry")
async def cb_redeem_no_expiry(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await _finalize_redeem_code(callback.message, state, expires_at=None)
    await callback.answer()


@router.message(AdminStates.redeem_create_expiry)
async def process_redeem_code_expiry(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.strip()
    expires_at = None
    if raw.lower() not in ("none", "no", "-", "skip"):
        try:
            from datetime import datetime as _dt
            _dt.strptime(raw, "%Y-%m-%d")
            expires_at = raw + "T23:59:59"
        except ValueError:
            await message.answer(
                "❌ Invalid date format. Use <code>YYYY-MM-DD</code> or type <code>none</code>.",
                parse_mode="HTML",
            )
            return
    await _finalize_redeem_code(message, state, expires_at=expires_at)


async def _finalize_redeem_code(msg, state: FSMContext, expires_at):
    data = await state.get_data()
    await state.clear()
    code = data["new_code"]
    amount = data["new_amount"]
    limit = data["new_limit"]
    try:
        code_id = await create_redeem_code(code, amount, limit, expires_at)
        exp_str = expires_at[:10] if expires_at else "No expiry"
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🎁 View All Codes", callback_data="admin:redeem_codes"))
        builder.row(InlineKeyboardButton(text="◀️ Admin Panel", callback_data="admin:main"))
        await msg.answer(
            f"✅ <b>Redeem Code Created!</b>\n\n"
            f"Code: <code>{code}</code>\n"
            f"Amount: <b>${amount:.2f}</b>\n"
            f"Usage limit: <b>{limit}</b>\n"
            f"Expires: <b>{exp_str}</b>\n"
            f"ID: <b>#{code_id}</b>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    except Exception as e:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:redeem_codes"))
        await msg.answer(
            f"❌ Failed to create code: <code>{e}</code>\n"
            f"(Code may already exist — codes must be unique.)",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("admin:redeem_del:"))
async def cb_redeem_delete(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    code_id = int(callback.data.split(":")[2])
    codes = await get_all_redeem_codes()
    target = next((c for c in codes if c["id"] == code_id), None)
    if not target:
        await callback.answer("Code not found.", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗑️ Yes, Delete", callback_data=f"admin:redeem_confirm_del:{code_id}"),
        InlineKeyboardButton(text="◀️ Cancel", callback_data="admin:redeem_codes"),
    )
    await callback.message.edit_text(
        f"🗑️ <b>Delete Redeem Code?</b>\n\n"
        f"Code: <code>{target['code']}</code>\n"
        f"Amount: <b>${target['amount']:.2f}</b>\n"
        f"Used: <b>{target['times_used']}/{target['usage_limit']}</b>\n\n"
        f"This cannot be undone.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:redeem_confirm_del:"))
async def cb_redeem_confirm_delete(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    code_id = int(callback.data.split(":")[2])
    await delete_redeem_code(code_id)
    await callback.answer("✅ Code deleted.", show_alert=True)
    codes = await get_all_redeem_codes()
    total = len(codes)
    active = sum(1 for c in codes if c["times_used"] < c["usage_limit"])
    await callback.message.edit_text(
        f"🎁 <b>Redeem Codes</b>\n\n"
        f"Total: <b>{total}</b> codes  •  Active: <b>{active}</b>\n\n"
        f"Tap a code to <b>delete</b> it, or create a new one:",
        reply_markup=admin_redeem_codes_kb(codes),
        parse_mode="HTML",
    )


# ─── Broadcast ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.broadcast_msg)
    await callback.message.edit_text(
        f"{pe('megaphone')} <b>BROADCAST</b>\n{DIVIDER}\n"
        f"Send your message below (supports <b>HTML</b> formatting).\n\n"
        f"{pe('bolt')} It will be sent with a premium <b>BACK IN STOCK</b> header "
        f"and a green <b>BUY NOW</b> button.",
        reply_markup=cancel_kb("admin:main"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.broadcast_msg)
async def process_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = message.text or ""
    if not text:
        await message.answer("❌ Empty message.")
        return
    await state.clear()
    users = await get_all_users()
    status_msg = await message.answer(f"📢 Broadcasting to <b>{len(users)}</b> users...", parse_mode="HTML")
    sent = failed = 0
    for u in users:
        try:
            await message.bot.send_message(
                u["telegram_id"],
                f"{pe('fire')} <b>BACK IN STOCK</b> {pe('fire')}\n"
                f"{DIVIDER}\n{text}\n{DIVIDER}\n"
                f"{pe('bolt')} <i>Limited stock — grab it now!</i>",
                reply_markup=broadcast_buy_kb(),
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(
        f"✅ <b>Broadcast Complete</b>\n\n✅ Delivered: <b>{sent}</b>\n❌ Failed: <b>{failed}</b>",
        parse_mode="HTML",
    )


# ─── Product-specific Alert Broadcast ────────────────────────────────────────

@router.callback_query(F.data == "admin:product_broadcast")
async def cb_product_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback): return
    products = await get_products(active_only=False)
    if not products:
        await callback.answer("No products found.", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for p in products:
        subs = await get_product_alert_subscribers(p["id"])
        builder.row(InlineKeyboardButton(
            text=f"{p['name']}  ({len(subs)} subscribers)",
            callback_data=f"admin:pb_select:{p['id']}",
        ))
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:main"))
    await callback.message.edit_text(
        "📣 <b>Product Alert Broadcast</b>\n\nPick a product — message will go to everyone who set an alert on it:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:pb_select:"))
async def cb_pb_select(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback): return
    product_id = int(callback.data.split(":")[2])
    product = await get_product(product_id)
    subs = await get_product_alert_subscribers(product_id)
    await state.set_state(AdminStates.product_broadcast_msg)
    await state.update_data(product_id=product_id, product_name=product["name"] if product else str(product_id))
    await callback.message.edit_text(
        f"📣 <b>Product Alert: {product['name'] if product else product_id}</b>\n\n"
        f"👥 Subscribers: <b>{len(subs)}</b>\n\n"
        f"Send the announcement message now (supports <b>HTML</b> formatting):",
        reply_markup=cancel_kb("admin:product_broadcast"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.product_broadcast_msg)
async def process_product_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Empty message.")
        return
    data = await state.get_data()
    await state.clear()
    product_id = data["product_id"]
    product_name = data.get("product_name", "Product")
    subs = await get_product_alert_subscribers(product_id)
    if not subs:
        await message.answer(f"⚠️ No subscribers for <b>{product_name}</b>.", parse_mode="HTML")
        return
    status_msg = await message.answer(
        f"📣 Sending to <b>{len(subs)}</b> alert subscriber(s) for <b>{product_name}</b>…",
        parse_mode="HTML",
    )
    sent = failed = 0
    for tg_id in subs:
        try:
            await message.bot.send_message(
                tg_id,
                f"{pe('fire')} <b>BACK IN STOCK</b> {pe('fire')}\n"
                f"{DIVIDER}\n"
                f"{pe('box')} <b>{product_name}</b>\n\n{text}\n{DIVIDER}\n"
                f"{pe('bolt')} <i>Limited stock — grab it now!</i>",
                reply_markup=broadcast_buy_kb(product_id),
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(
        f"✅ <b>Alert Sent</b>\n\n"
        f"📦 Product: <b>{product_name}</b>\n"
        f"✅ Delivered: <b>{sent}</b>\n"
        f"❌ Failed: <b>{failed}</b>",
        parse_mode="HTML",
    )


# ─── Low Stock Threshold ──────────────────────────────────────────────────────

@router.message(Command("setlowstock"))
async def cmd_setlowstock(message: Message, state: FSMContext):
    """Set the low-stock alert threshold.

    Usage:
      /setlowstock        — show current threshold
      /setlowstock <n>    — set threshold to n (integer ≥ 0)
    """
    if not is_admin(message.from_user.id):
        return

    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        # No argument — show current value
        current = await get_setting("low_stock_threshold")
        try:
            threshold = int(current)
        except (TypeError, ValueError):
            threshold = 3
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="✏️ Change Threshold", callback_data="admin:edit_low_stock"))
        builder.row(InlineKeyboardButton(text="◀️ Back to Admin", callback_data="admin:main"))
        await message.answer(
            f"🔔 <b>Low Stock Alert Threshold</b>\n\n"
            f"Current threshold: <b>{threshold}</b>\n\n"
            f"Admins receive a low-stock warning when remaining units drop to this number.\n\n"
            f"To update: <code>/setlowstock &lt;number&gt;</code>\n"
            f"Example: <code>/setlowstock 5</code>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        return

    raw = parts[1].strip()
    try:
        new_threshold = int(raw)
        if new_threshold < 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Please enter a valid non-negative integer.\n"
            "Example: <code>/setlowstock 5</code>",
            parse_mode="HTML",
        )
        return

    await set_setting("low_stock_threshold", str(new_threshold))
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back to Admin", callback_data="admin:main"))
    await message.answer(
        f"✅ <b>Low Stock Threshold Updated</b>\n\n"
        f"New threshold: <b>{new_threshold}</b>\n\n"
        f"You will be alerted when any product's remaining stock drops to "
        f"<b>{new_threshold}</b> unit{'s' if new_threshold != 1 else ''}.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:low_stock_settings")
async def cb_low_stock_settings(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    current = await get_setting("low_stock_threshold")
    try:
        threshold = int(current)
    except (TypeError, ValueError):
        threshold = 3
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Change Threshold", callback_data="admin:edit_low_stock"))
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))
    await callback.message.edit_text(
        f"🔔 <b>Low Stock Alert Threshold</b>\n\n"
        f"Current threshold: <b>{threshold}</b>\n\n"
        f"Admins receive a warning when remaining stock for any product drops to this number after a sale.\n\n"
        f"Tap the button below to change it:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:edit_low_stock")
async def cb_edit_low_stock(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(AdminStates.editing_low_stock_threshold)
    await callback.message.edit_text(
        "✏️ <b>Set Low Stock Threshold</b>\n\n"
        "Enter the new threshold (a non-negative integer).\n"
        "Example: <code>5</code>\n\n"
        "Set to <code>0</code> to disable low-stock warnings.",
        reply_markup=cancel_kb("admin:low_stock_settings"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.editing_low_stock_threshold)
async def process_edit_low_stock_threshold(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        threshold = int((message.text or "").strip())
        if threshold < 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Please enter a valid non-negative integer (e.g. <code>5</code>).",
            parse_mode="HTML",
        )
        return
    await state.clear()
    await set_setting("low_stock_threshold", str(threshold))
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back to Low Stock Settings", callback_data="admin:low_stock_settings"))
    unit_word = "unit" if threshold == 1 else "units"
    detail = (
        "Low-stock warnings are now <b>disabled</b> (threshold = 0)."
        if threshold == 0
        else f"You will be alerted when stock drops to <b>{threshold}</b> {unit_word}."
    )
    await message.answer(
        f"✅ Low stock threshold updated to <b>{threshold}</b>.\n\n{detail}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


# ── Email delivery — mark as done ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:email_done:"))
async def cb_email_done(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    parts = callback.data.split(":")
    order_id = parts[2]
    user_tg_id = int(parts[3])

    # Notify buyer
    try:
        await callback.bot.send_message(
            user_tg_id,
            f"✅ <b>Order #{order_id} Delivered!</b>\n\n"
            f"Your product has been sent to your email.\n"
            f"Check your inbox (and spam folder) 📬",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Could not notify buyer {user_tg_id}: {e}")

    # Update the admin message
    try:
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>Marked as delivered</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("✅ Marked as delivered!")
