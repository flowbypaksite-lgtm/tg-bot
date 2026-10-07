import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from bot.utils.ui import DIVIDER, pe
from bot.keyboards.menus import shop_products_kb, product_detail_kb, buy_confirm_kb, back_to_main_kb, checkout_payment_kb
from bot.database import (
    get_products, get_product, create_order, claim_stock_item,
    complete_order, refund_order, get_membership_discount, get_user,
    auto_upgrade_membership, get_referrals, pay_referral_bonus,
    has_claimed_free_product, toggle_product_alert, has_product_alert,
    create_pending_deposit, use_redeem_code,
)
from bot.database import get_setting as _get_setting
from bot.config import ADMIN_IDS, FREEBIE_CHANNEL, SALES_GROUP_ID, BOT_USERNAME

router = Router()
logger = logging.getLogger(__name__)

SURFSHARK_CHANNEL = FREEBIE_CHANNEL   # same join gate


async def _safe_edit_text(callback, text: str, reply_markup=None, parse_mode: str = "HTML"):
    """Edit message text. If the current message is a photo, delete it and send fresh text."""
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.bot.send_message(
            callback.message.chat.id, text, reply_markup=reply_markup, parse_mode=parse_mode
        )


class SurfsharkFlow(StatesGroup):
    collecting_codes = State()


class ShopStates(StatesGroup):
    custom_qty = State()
    checkout_screenshot = State()
    checkout_order_id = State()
    checkout_redeem = State()
    delivery_email = State()


async def _is_channel_member(bot, user_id: int, channel: str) -> bool:
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status in ("creator", "administrator", "member", "restricted")
    except Exception:
        return False


@router.callback_query(F.data == "menu:shop")
async def cb_shop(callback: CallbackQuery, db_user: dict):
    # Paid products only — free tools live in the Freebies section.
    products = [p for p in await get_products(active_only=True)
                if (p.get("price") or 0) > 0]
    if not products:
        await callback.message.edit_text(
            "🛍️ <b>Shop</b>\n\nNo products available right now. Check back soon!",
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    count = len(products)

    in_stock = sum(1 for p in products if (p.get("stock_count", 0) or 0) > 0)
    text = (
        f"{pe('shop')} <b>PREMIUM STORE</b> {pe('crown')}\n"
        f"{DIVIDER}\n"
        f"{pe('box')} Products: <b>{count}</b>\n"
        f"{pe('check')} In stock: <b>{in_stock}</b>   {pe('cross')} Sold out: "
        f"<b>{count - in_stock}</b>\n"
        f"{pe('wallet')} Balance: <b>${db_user['balance']:.2f}</b>\n"
        f"{DIVIDER}\n"
        f"{pe('bolt')} <i>Green = available · Red = sold out</i>\n"
        f"Tap a product to view details:"
    )
    await _safe_edit_text(callback, text, reply_markup=shop_products_kb(products))
    await callback.answer()


@router.callback_query(F.data.startswith("shop:prod:"))
async def cb_product_detail(callback: CallbackQuery, db_user: dict, state: FSMContext):
    await state.clear()   # cancel any active flow when browsing
    product_id = int(callback.data.split(":")[2])
    product = await get_product(product_id)
    if not product:
        await callback.answer("❌ Product not found.", show_alert=True)
        return

    price = product.get("price", 0)
    is_free = price == 0.0
    is_surfshark = "surfshark" in product.get("name", "").lower()

    discount = await get_membership_discount(db_user) if not is_free else 0.0
    original_price = product["price"]
    final_price = round(original_price * (1 - discount), 2)

    if is_free:
        price_display = "<b>FREE 🎉</b>"
    elif discount > 0:
        price_display = (
            f"<s>${original_price:.2f}</s> → <b>${final_price:.2f}</b> "
            f"({int(discount * 100)}% tier discount 👑)"
        )
    else:
        price_display = f"<b>${original_price:.2f}</b>"

    if is_surfshark:
        avail_line = "🔓 Join channel to activate"
    elif is_free:
        stock_left = product.get("stock_count", 0)
        avail_line = f"🎟️ {stock_left} code(s) remaining"
    else:
        avail_line = "✅ Available — order & we deliver manually"

    import json as _json
    logo = product.get("logo") or "🏷️"
    alert_on = await has_product_alert(callback.from_user.id, product_id)
    try:
        custom_btns = _json.loads(product.get("custom_buttons") or "[]")
    except Exception:
        custom_btns = []
    kb = product_detail_kb(product_id, qty=1, unit_price=final_price, is_free=is_free, has_alert=alert_on, custom_buttons=custom_btns)

    # ── Structured detail lines ──────────────────────────────────────────────
    warranty      = product.get("warranty")      or "No Warranty"
    product_type  = product.get("product_type")  or "Account"
    delivery_type = product.get("delivery_type") or ("Automatic" if product.get("stock_count", 0) > 0 else "Manual")

    # Description: split lines and prefix each with ⚡
    raw_desc = (product.get("description") or "").strip()
    if raw_desc:
        desc_lines = "\n".join(f"⚡ {line.strip()}" for line in raw_desc.splitlines() if line.strip())
        desc_block = f"\n\n<b>📊 Product Description</b>\n{'━'*19}\n{desc_lines}"
    else:
        desc_block = ""

    text = (
        f"{logo} <b>{product['name']}</b>\n\n"
        f"💰 Price: {price_display}\n"
        f"📦 Stock:  <b>{product.get('stock_count', 0)}</b>\n"
        f"🛡 Warranty:  <b>{warranty}</b>\n"
        f"🏷 Product Type:  <b>{product_type}</b>\n"
        f"🚚 Delivery Type:  <b>{delivery_type}</b>"
        f"{desc_block}"
    )

    logo_file_id = product.get("logo_file_id")
    if logo_file_id:
        # Show the Telegram photo above product info
        await callback.answer()
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.bot.send_photo(
            callback.message.chat.id,
            photo=logo_file_id,
            caption=text,
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await _safe_edit_text(callback, text, reply_markup=kb)
        await callback.answer()


# ── Qty controls and noop ────────────────────────────────────────────────────

@router.callback_query(F.data == "shop:noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("shop:setqty:"))
async def cb_set_qty(callback: CallbackQuery, db_user: dict):
    """Tap a preset quantity button."""
    parts = callback.data.split(":")
    product_id = int(parts[2])
    new_qty = int(parts[3])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Product not found.", show_alert=True)
        return
    discount = await get_membership_discount(db_user)
    unit_price = round(product["price"] * (1 - discount), 2)
    alert_on = await has_product_alert(callback.from_user.id, product_id)
    await callback.message.edit_reply_markup(
        reply_markup=product_detail_kb(product_id, qty=new_qty, unit_price=unit_price, has_alert=alert_on)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop:customqty:"))
async def cb_custom_qty_prompt(callback: CallbackQuery, state: FSMContext):
    """Ask user to type a custom quantity."""
    product_id = int(callback.data.split(":")[2])
    await state.set_state(ShopStates.custom_qty)
    await state.update_data(product_id=product_id, origin_chat_id=callback.message.chat.id)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data=f"shop:prod:{product_id}"))
    await callback.message.edit_text(
        "✏️ <b>Custom Quantity</b>\n\nSend the number you want to buy:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ShopStates.custom_qty)
async def cb_custom_qty_input(message: Message, state: FSMContext, db_user: dict):
    data = await state.get_data()
    product_id = data.get("product_id")
    await state.clear()
    try:
        qty = int(message.text.strip())
        if qty < 1:
            raise ValueError
    except (ValueError, AttributeError):
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"shop:prod:{product_id}"))
        await message.answer("❌ Please enter a valid number (1 or more).", reply_markup=builder.as_markup())
        return
    product = await get_product(product_id)
    if not product:
        await message.answer("❌ Product not found.")
        return
    discount = await get_membership_discount(db_user)
    unit_price = round(product["price"] * (1 - discount), 2)
    alert_on = await has_product_alert(message.from_user.id, product_id)
    await message.answer(
        f"✅ Quantity set to <b>{qty}</b>  —  Total: <b>${round(unit_price * qty, 2):.2f}</b>",
        reply_markup=product_detail_kb(product_id, qty=qty, unit_price=unit_price, has_alert=alert_on),
        parse_mode="HTML",
    )


# ── Custom button text popup ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("shop:cbtn:"))
async def cb_custom_btn(callback: CallbackQuery):
    import json as _json
    parts = callback.data.split(":")
    product_id = int(parts[2])
    btn_index = int(parts[3])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Product not found.", show_alert=True)
        return
    try:
        btns = _json.loads(product.get("custom_buttons") or "[]")
        btn = btns[btn_index]
        text = btn.get("value", "")
    except Exception:
        text = ""
    await callback.answer(text[:200] if text else "—", show_alert=True)


# ── Price Alert toggle ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("shop:alert:"))
async def cb_product_alert(callback: CallbackQuery, db_user: dict):
    product_id = int(callback.data.split(":")[2])
    product = await get_product(product_id)
    if not product:
        await callback.answer("Product not found.", show_alert=True)
        return
    added = await toggle_product_alert(callback.from_user.id, product_id)
    if added:
        await callback.answer("🔔 Alert set! You'll be notified about this product.", show_alert=True)
    else:
        await callback.answer("🔕 Alert removed.", show_alert=True)
    # Refresh keyboard with new alert state
    discount = await get_membership_discount(db_user)
    unit_price = round(product["price"] * (1 - discount), 2)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=product_detail_kb(product_id, qty=1, unit_price=unit_price, has_alert=added)
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("shop:buy:"))
async def cb_buy(callback: CallbackQuery, db_user: dict, state: FSMContext):
    parts = callback.data.split(":")
    product_id = int(parts[2])
    qty = int(parts[3]) if len(parts) > 3 else 1
    product = await get_product(product_id)
    if not product:
        await callback.answer("❌ Product not found.", show_alert=True)
        return

    # ── Surfshark special flow (channel-join + code collection) ───────────────
    if "surfshark" in product.get("name", "").lower():
        # Answer immediately so the button never hangs/spins
        await callback.answer("🔍 Checking membership…")

        joined = await _is_channel_member(callback.bot, callback.from_user.id, SURFSHARK_CHANNEL)

        if not joined:
            # Show join gate (only edit if we're not already on that screen)
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(
                text=f"📢 Join {SURFSHARK_CHANNEL}",
                url=f"https://t.me/{SURFSHARK_CHANNEL.lstrip('@')}",
            ))
            builder.row(InlineKeyboardButton(
                text="✅ I've Joined — Check",
                callback_data=f"shop:buy:{product_id}:1",
            ))
            builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"shop:prod:{product_id}"))
            gate_text = (
                f"📢 <b>Channel Required</b>\n\n"
                f"You must join <b>{SURFSHARK_CHANNEL}</b> to activate Surfshark VPN.\n\n"
                f"Tap the button below to join, then come back and tap <b>I've Joined</b>.\n\n"
                f"❌ <b>Not joined yet.</b> Please join the channel first!"
            )
            try:
                await _safe_edit_text(callback, gate_text, reply_markup=builder.as_markup())
            except Exception:
                pass  # "message not modified" — fine, user sees the alert
            return

        # ✅ Channel verified — show activation instructions
        await state.set_state(SurfsharkFlow.collecting_codes)
        await state.update_data(product_id=product_id)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data=f"shop:prod:{product_id}"))
        await _safe_edit_text(callback,
            "✅ <b>Membership confirmed!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Now activate your VPN:\n\n"
            "1. Open the <b>SurfShark app</b>\n"
            "2. Go to <b>My Account → Login With Code</b>\n"
            "3. A <b>6-character code</b> will appear (e.g. A3F7K2)\n"
            "4. Type or paste the code here 👇\n\n"
            "⚠️ Browser logins are NOT allowed — only the SurfShark app or browser extension.\n\n"
            "You can send as many codes as needed. Tap Cancel to stop.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        return

    # ── Free product with stock (e.g. coupon codes) ─────────────────────────
    if product.get("price", 1) == 0.0:
        # Answer immediately — channel check can be slow
        await callback.answer("🔍 Checking membership…")

        from bot.handlers.freebies import is_channel_member
        from bot.config import FREEBIE_CHANNEL
        joined = await is_channel_member(callback.bot, callback.from_user.id)

        if not joined:
            channel_url = f"https://t.me/{FREEBIE_CHANNEL.lstrip('@')}"
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(
                text=f"📢 Join {FREEBIE_CHANNEL}",
                url=channel_url,
            ))
            builder.row(InlineKeyboardButton(
                text="✅ I've Joined — Check",
                callback_data=f"shop:buy:{product_id}:1",
            ))
            builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"shop:prod:{product_id}"))
            gate_text = (
                f"📢 <b>Channel Required</b>\n\n"
                f"You must join <b>{FREEBIE_CHANNEL}</b> to claim this free product.\n\n"
                f"Tap Join below, then come back and tap <b>I've Joined</b>."
            )
            try:
                await _safe_edit_text(callback, gate_text, reply_markup=builder.as_markup())
            except Exception:
                pass
            return

        # Channel verified — now do pre-claim checks
        if await has_claimed_free_product(db_user["id"], product_id):
            await _safe_edit_text(
                callback,
                "❌ <b>Already Claimed</b>\n\nYou've already claimed this free product.",
                reply_markup=InlineKeyboardBuilder().row(
                    InlineKeyboardButton(text="◀️ Back", callback_data=f"shop:prod:{product_id}")
                ).as_markup(),
            )
            return
        if product.get("stock_count", 0) <= 0:
            await _safe_edit_text(
                callback,
                "❌ <b>Out of Stock</b>\n\nAll codes have been claimed — check back soon!",
                reply_markup=InlineKeyboardBuilder().row(
                    InlineKeyboardButton(text="◀️ Back", callback_data=f"shop:prod:{product_id}")
                ).as_markup(),
            )
            return

        logo = product.get("logo") or "🎟️"
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🎟️ Claim Free Code", callback_data=f"shop:confirm:{product_id}:1"))
        builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"shop:prod:{product_id}"))
        await _safe_edit_text(
            callback,
            f"{logo} <b>{product['name']}</b>\n\n"
            f"✅ Channel verified!\n"
            f"📦 {product.get('stock_count', 0)} code(s) remaining\n\n"
            f"Claim your <b>FREE</b> promo code now?",
            reply_markup=builder.as_markup(),
        )
        return

    # ── Normal paid product: show payment method selection ──────────────────
    discount = await get_membership_discount(db_user)
    unit_price = round(product["price"] * (1 - discount), 2)
    total_price = round(unit_price * qty, 2)

    discount_line = ""
    if discount > 0:
        discount_line = f"\n🏷️ Discount ({int(discount*100)}% off): -${round(product['price'] - unit_price, 2):.2f} per item"
    qty_line = f"\n🔢 Quantity: <b>{qty}x</b>" if qty > 1 else ""

    text = (
        f"🛒 <b>Select Payment Method</b>\n\n"
        f"Product: <b>{product['name']}</b>\n"
        f"Unit price: <b>${unit_price:.2f}</b>"
        f"{discount_line}"
        f"{qty_line}\n"
        f"<b>Total: ${total_price:.2f}</b>"
    )
    await _safe_edit_text(callback, text, reply_markup=checkout_payment_kb(product_id, qty, total_price))
    await callback.answer()


# ── Wallet pay (order confirmation step) ────────────────────────────────────

@router.callback_query(F.data.startswith("shop:wallet_pay:"))
async def cb_wallet_pay(callback: CallbackQuery, db_user: dict):
    parts = callback.data.split(":")
    product_id = int(parts[2])
    qty = int(parts[3])
    product = await get_product(product_id)
    if not product:
        await callback.answer("❌ Product not found.", show_alert=True)
        return

    discount = await get_membership_discount(db_user)
    unit_price = round(product["price"] * (1 - discount), 2)
    total_price = round(unit_price * qty, 2)

    if db_user["balance"] < total_price:
        shortage = total_price - db_user["balance"]
        await callback.answer(
            f"❌ Insufficient balance!\nYou need ${shortage:.2f} more.\nGo to 💰 Wallet → Add Balance.",
            show_alert=True,
        )
        return

    discount_line = ""
    if discount > 0:
        discount_line = f"\n🏷️ Discount ({int(discount*100)}% off): -${round(product['price'] - unit_price, 2):.2f} per item"
    qty_line = f"\n🔢 Quantity: <b>{qty}x</b>" if qty > 1 else ""

    text = (
        f"💳 <b>Order Confirmation</b>\n\n"
        f"Product: <b>{product['name']}</b>\n"
        f"Unit price: <b>${unit_price:.2f}</b>"
        f"{discount_line}"
        f"{qty_line}\n"
        f"<b>Total: ${total_price:.2f}</b>\n\n"
        f"Your balance: <b>${db_user['balance']:.2f}</b>\n"
        f"After purchase: <b>${db_user['balance'] - total_price:.2f}</b>\n\n"
        f"⏳ Order will be <b>delivered manually</b> by the team.\n\n"
        f"Confirm your purchase?"
    )
    await _safe_edit_text(callback, text, reply_markup=buy_confirm_kb(product_id, qty, total_price))
    await callback.answer()


# ── Direct pay at checkout ────────────────────────────────────────────────────

METHOD_NAMES = {
    "sadapay":    "💳 SadaPay",
    "binancepay": "💛 Binance Pay",
    "trc20":      "♦️ USDT TRC20",
    "bep20":      "💠 USDT BEP20",
}


@router.callback_query(F.data.startswith("shop:checkout_method:"))
async def cb_checkout_method(callback: CallbackQuery, state: FSMContext, db_user: dict):
    parts = callback.data.split(":")
    product_id = int(parts[2])
    qty = int(parts[3])
    method = parts[4]

    product = await get_product(product_id)
    if not product:
        await callback.answer("❌ Product not found.", show_alert=True)
        return

    discount = await get_membership_discount(db_user)
    unit_price = round(product["price"] * (1 - discount), 2)
    total_price = round(unit_price * qty, 2)

    # Redeem code flow
    if method == "redeem":
        await state.set_state(ShopStates.checkout_redeem)
        await state.update_data(product_id=product_id, qty=qty, total_price=total_price)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data=f"shop:buy:{product_id}:{qty}"))
        await _safe_edit_text(
            callback,
            f"🎁 <b>Redeem Code Checkout</b>\n\n"
            f"Product: <b>{product['name']}</b>\n"
            f"Total: <b>${total_price:.2f}</b>\n\n"
            f"Enter your redeem code:",
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return

    if method not in METHOD_NAMES:
        await callback.answer("Invalid payment method.", show_alert=True)
        return

    method_name = METHOD_NAMES[method]

    # Get payment address from settings
    if method == "sadapay":
        payment_detail = await _get_setting("sadapay_number")
        instructions = (
            f"💳 <b>SadaPay — Direct Checkout</b>\n\n"
            f"Send exactly <b>${total_price:.2f}</b> to:\n\n"
            f"📱 <b>SadaPay Number:</b>\n"
            f"<code>{payment_detail}</code>\n\n"
            f"⚠️ Send exactly <b>${total_price:.2f}</b> — no more, no less.\n"
            f"After sending, take a screenshot and send it here."
        )
    elif method == "binancepay":
        payment_detail = await _get_setting("binance_pay_id")
        instructions = (
            f"💛 <b>Binance Pay — Direct Checkout</b>\n\n"
            f"Send exactly <b>${total_price:.2f} USDT</b> via Binance Pay to:\n\n"
            f"🆔 <b>Binance Pay ID:</b>\n"
            f"<code>{payment_detail}</code>\n\n"
            f"⚠️ Use Binance Pay only — not a wallet address!\n"
            f"After sending, take a screenshot and send it here."
        )
    elif method == "trc20":
        payment_detail = await _get_setting("binance_trc20")
        instructions = (
            f"♦️ <b>USDT TRC20 — Direct Checkout</b>\n\n"
            f"Send exactly <b>${total_price:.2f} USDT</b> (TRC20 network) to:\n\n"
            f"📋 <b>Wallet Address:</b>\n"
            f"<code>{payment_detail}</code>\n\n"
            f"⚠️ Use TRC20 network only!\n"
            f"After sending, take a screenshot and send it here."
        )
    else:
        payment_detail = await _get_setting("binance_bep20")
        instructions = (
            f"💠 <b>USDT BEP20 — Direct Checkout</b>\n\n"
            f"Send exactly <b>${total_price:.2f} USDT</b> (BEP20/BSC network) to:\n\n"
            f"📋 <b>Wallet Address:</b>\n"
            f"<code>{payment_detail}</code>\n\n"
            f"⚠️ Use BEP20/BSC network only!\n"
            f"After sending, take a screenshot and send it here."
        )

    await state.set_state(ShopStates.checkout_screenshot)
    await state.update_data(
        product_id=product_id, qty=qty,
        total_price=total_price, method=method,
    )
    from bot.utils.ui import green as _green, red as _red, sky as _sky
    auto = method in ("binancepay", "trc20", "bep20") and await _binance_auto_enabled()
    builder = InlineKeyboardBuilder()
    if auto:
        builder.row(_green(f"{pe('bolt')} Auto Verify (Order ID)",
                           callback_data="shop:auto_verify"))
    builder.row(_sky("📸 Send Screenshot", callback_data="shop:manual_proof"))
    builder.row(_red("❌ Cancel", callback_data=f"shop:buy:{product_id}:{qty}"))
    tail = (
        f"\n\n{DIVIDER}\n{pe('bolt')} <b>INSTANT:</b> tap <b>Auto Verify</b> and send "
        f"your Binance <b>Order ID / TxID</b> — it is checked automatically."
        if auto else "\n\n📸 <b>Send your payment screenshot below:</b>"
    )
    await _safe_edit_text(callback, instructions + tail, reply_markup=builder.as_markup())
    await callback.answer()


# ── Binance auto verification at checkout ───────────────────────────────────

async def _binance_auto_enabled() -> bool:
    from bot.config import BINANCE_API_KEY, BINANCE_API_SECRET
    return (
        (await _get_setting("binance_auto_enabled")) == "1"
        and bool(BINANCE_API_KEY and BINANCE_API_SECRET)
    )


@router.callback_query(F.data == "shop:manual_proof")
async def cb_shop_manual_proof(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ShopStates.checkout_screenshot)
    await callback.answer("📸 Send the screenshot now.")


@router.callback_query(F.data == "shop:auto_verify")
async def cb_shop_auto_verify(callback: CallbackQuery, state: FSMContext):
    from bot.utils.ui import red as _red, sky as _sky
    data = await state.get_data()
    if not data.get("total_price"):
        await callback.answer("Start the checkout again please.", show_alert=True)
        return
    await state.set_state(ShopStates.checkout_order_id)
    builder = InlineKeyboardBuilder()
    builder.row(_sky("📸 Send Screenshot Instead", callback_data="shop:manual_proof"))
    builder.row(_red("❌ Cancel", callback_data="menu:shop"))
    await callback.message.answer(
        f"{pe('bolt')} <b>AUTO PAYMENT VERIFICATION</b>\n"
        f"{DIVIDER}\n"
        f"Send your Binance <b>Order ID</b> or <b>TxID</b>.\n\n"
        f"{pe('shield')} We match <b>order id + amount (${data['total_price']:.2f}) + time</b> "
        f"with a read-only key.",
        reply_markup=builder.as_markup(), parse_mode="HTML",
    )
    await callback.answer()


@router.message(ShopStates.checkout_order_id)
async def process_checkout_order_id(message: Message, state: FSMContext, db_user: dict):
    from bot.config import ADMIN_IDS, BINANCE_API_KEY, BINANCE_API_SECRET
    from bot.database import (get_used_binance_ids, is_binance_id_used,
                              record_binance_payment, update_balance)
    from bot.utils.binance import verify_payment
    from bot.utils.ui import green as _green, red as _red, sky as _sky

    order_id = (message.text or "").strip()
    if len(order_id) < 6:
        await message.answer("❌ Send a valid Binance Order ID / TxID.")
        return
    if await is_binance_id_used(order_id):
        await message.answer("❌ This Order ID has already been used.")
        return

    data = await state.get_data()
    total_price = data.get("total_price", 0.0)
    product_id = data.get("product_id")
    qty = data.get("qty", 1)

    status = await message.answer(f"{pe('clock')} Checking Binance…", parse_mode="HTML")
    window = int((await _get_setting("binance_window_hours")) or 24)
    amount_only = (await _get_setting("binance_amount_only")) == "1"

    try:
        match = await verify_payment(
            BINANCE_API_KEY, BINANCE_API_SECRET, order_id, total_price,
            window_hours=window, used_ids=set(await get_used_binance_ids()),
            allow_amount_only=amount_only,
        )
    except Exception:
        logger.exception("Binance checkout verification failed")
        match = None

    builder = InlineKeyboardBuilder()
    if match is None or not match.ok:
        reason = "Binance is unreachable right now." if match is None else {
            "not_found": "No matching payment found yet — wait a minute and retry.",
            "amount_mismatch": "Payment found but the amount does not match.",
            "already_used": "This Order ID was already used.",
            "too_old": "That payment is outside the allowed time window.",
            "outgoing": "That transaction is not a payment to us.",
            "wrong_currency": "Only USDT / stablecoins are accepted.",
            "no_transactions": "No recent transactions found.",
            "not_configured": "Auto verification is off — please send a screenshot.",
        }.get(match.reason, "Payment could not be verified.")
        builder.row(_green(f"{pe('bolt')} Try Again", callback_data="shop:auto_verify"))
        builder.row(_sky("📸 Send Screenshot Instead", callback_data="shop:manual_proof"))
        builder.row(_red("❌ Cancel", callback_data="menu:shop"))
        await status.edit_text(
            f"{pe('cross')} <b>Payment not verified</b>\n{DIVIDER}\n{reason}",
            reply_markup=builder.as_markup(), parse_mode="HTML",
        )
        return

    await state.clear()
    credited = round(match.amount or total_price, 2)
    await update_balance(db_user["id"], credited, "deposit",
                         f"Binance auto payment ({match.order_id})")
    await record_binance_payment(
        order_id=match.order_id, user_id=db_user["id"],
        telegram_id=message.from_user.id, amount=credited,
        currency=match.currency or "USDT", source=match.source or "checkout",
        purpose="purchase",
    )

    if product_id:
        builder.row(_green(f"{pe('cart')} Complete Order Now",
                           callback_data=f"shop:wallet_pay:{product_id}:{qty}"))
    builder.row(_sky("🏠 Main Menu", callback_data="menu:main"))
    await status.edit_text(
        f"{pe('check')} <b>PAYMENT VERIFIED</b> {pe('sparkles')}\n"
        f"{DIVIDER}\n"
        f"{pe('money')} Amount: <b>${credited:.2f}</b>\n"
        f"🧾 Order ID: <code>{match.order_id}</code>\n"
        f"{DIVIDER}\n"
        f"{pe('bolt')} Funds added to your wallet — tap <b>Complete Order</b> to "
        f"receive your product instantly.",
        reply_markup=builder.as_markup(), parse_mode="HTML",
    )
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f"{pe('check')} <b>Binance auto payment</b> @"
                f"{message.from_user.username or message.from_user.id} — "
                f"${credited:.2f} <code>{match.order_id}</code>",
                parse_mode="HTML")
        except Exception:
            pass


@router.message(ShopStates.checkout_screenshot)
async def cb_checkout_screenshot(message: Message, state: FSMContext, db_user: dict):
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id
    else:
        await message.answer("📸 Please send a <b>photo/screenshot</b> of your payment.", parse_mode="HTML")
        return

    data = await state.get_data()
    product_id = data["product_id"]
    qty = data["qty"]
    total_price = data["total_price"]
    method = data["method"]
    await state.clear()

    product = await get_product(product_id)
    product_name = product["name"] if product else f"Product #{product_id}"

    deposit_id = await create_pending_deposit(
        user_id=db_user["id"],
        telegram_id=message.from_user.id,
        amount=total_price,
        method=method,
        screenshot_file_id=file_id,
        checkout_product_id=product_id,
        checkout_qty=qty,
    )

    # Notify admins
    from bot.config import ADMIN_IDS as _ADMIN_IDS
    from bot.keyboards.menus import admin_deposit_approval_kb
    method_label = METHOD_NAMES.get(method, method)
    admin_text = (
        f"🛒 <b>Checkout Payment Request #{deposit_id}</b>\n\n"
        f"👤 {message.from_user.first_name or 'N/A'} (@{message.from_user.username or 'no_username'})\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Product: <b>{product_name}</b> x{qty}\n"
        f"💵 Amount: <b>${total_price:.2f}</b>\n"
        f"💳 Method: <b>{method_label}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Approve to credit balance + auto-deliver the product.</i>"
    )
    approval_kb = admin_deposit_approval_kb(deposit_id)
    for admin_id in _ADMIN_IDS:
        try:
            await message.bot.send_photo(admin_id, photo=file_id, caption=admin_text,
                                         reply_markup=approval_kb, parse_mode="HTML")
        except Exception:
            try:
                await message.bot.send_message(admin_id, admin_text,
                                               reply_markup=approval_kb, parse_mode="HTML")
            except Exception:
                pass

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))
    await message.answer(
        f"✅ <b>Payment Screenshot Received!</b>\n\n"
        f"📦 Product: <b>{product_name}</b>\n"
        f"💵 Amount: <b>${total_price:.2f}</b>\n"
        f"Reference: <b>#{deposit_id}</b>\n\n"
        f"⏳ Admin will verify and deliver your order shortly.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(ShopStates.checkout_redeem)
async def cb_checkout_redeem(message: Message, state: FSMContext, db_user: dict):
    code = (message.text or "").strip().upper()
    data = await state.get_data()
    product_id = data["product_id"]
    qty = data["qty"]
    total_price = data["total_price"]

    result = await use_redeem_code(code, db_user["id"])
    if not result["success"]:
        await message.answer(f"❌ {result['message']}\n\nSend another code or tap Cancel.")
        return

    credited = result["amount"]
    await state.clear()

    builder = InlineKeyboardBuilder()
    if credited >= total_price:
        builder.row(InlineKeyboardButton(text=f"✅ Buy Now (${total_price:.2f})", callback_data=f"shop:wallet_pay:{product_id}:{qty}"))
        builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))
        await message.answer(
            f"🎁 <b>Code Redeemed!</b>\n\n"
            f"+${credited:.2f} added to your wallet.\n"
            f"Your balance is now sufficient to complete this purchase.\n\n"
            f"Tap <b>Buy Now</b> to confirm your order.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    else:
        builder.row(InlineKeyboardButton(text="🛒 Back to Shop", callback_data="menu:shop"))
        await message.answer(
            f"🎁 <b>Code Redeemed!</b>\n\n"
            f"+${credited:.2f} added to your wallet.\n\n"
            f"⚠️ Your wallet may still not cover the full ${total_price:.2f} — "
            f"top it up further via Wallet → Add Balance, then come back to buy.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )


# ── Surfshark code collection ───────────────────────────────────────────────

@router.message(SurfsharkFlow.collecting_codes)
async def handle_surfshark_code(message: Message, state: FSMContext, db_user: dict):
    code = (message.text or "").strip()
    if not code:
        await message.answer("❌ Please send the code as text.")
        return

    user_info = (
        f"👤 {message.from_user.first_name or 'N/A'} "
        f"(@{message.from_user.username or 'no_username'}) "
        f"[ID: <code>{message.from_user.id}</code>]"
    )
    admin_text = (
        f"🦈 <b>Surfshark Activation Code</b>\n\n"
        f"From: {user_info}\n\n"
        f"<b>Code:</b> <code>{code}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(admin_id, admin_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel / Done", callback_data="menu:shop"))
    await message.answer(
        "✅ <b>Code received!</b> We'll activate it shortly.\n\n"
        "You can send another code if needed, or tap Cancel when done.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("shop:confirm:"))
async def cb_confirm_buy(callback: CallbackQuery, db_user: dict):
    parts = callback.data.split(":")
    product_id = int(parts[2])
    qty = int(parts[3]) if len(parts) > 3 else 1
    product = await get_product(product_id)
    if not product:
        await callback.answer("❌ Product not found.", show_alert=True)
        return

    is_free = product.get("price", 1) == 0.0

    # One-per-user check for free products
    if is_free and await has_claimed_free_product(db_user["id"], product_id):
        await callback.answer("❌ You've already claimed this free product!", show_alert=True)
        return

    discount = await get_membership_discount(db_user) if not is_free else 0.0
    unit_price = 0.0 if is_free else round(product["price"] * (1 - discount), 2)
    final_price = round(unit_price * qty, 2)

    # Balance check (skip for free products)
    if not is_free:
        fresh_user = await get_user(callback.from_user.id)
        if not fresh_user or fresh_user["balance"] < final_price:
            await callback.answer("❌ Insufficient balance!", show_alert=True)
            return

    # Create order (deducts balance atomically — $0 deducts nothing)
    order_id = await create_order(db_user["id"], product_id, final_price)

    # ── FREE product: claim a stock item (coupon codes) ──────────────────────
    if is_free:
        account_data = await claim_stock_item(product_id, db_user["id"], order_id)
        if not account_data:
            await refund_order(order_id, db_user["id"], 0.0)
            await callback.answer("❌ All codes have been claimed!", show_alert=True)
            return
        await complete_order(order_id)
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🛍️ Shop", callback_data="menu:shop"),
            InlineKeyboardButton(text="🏠 Menu", callback_data="menu:main"),
        )
        await callback.message.edit_text(
            f"✅ <b>Code Claimed!</b>\n\n"
            f"Product: <b>{product['name']}</b>\n"
            f"Order: <b>#{order_id}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎟️ <b>Your Promo Code:</b>\n\n"
            f"<code>{account_data}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Tap the link to activate your promo.</i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer("✅ Claimed!")
        return

    # ── PAID product: complete order + notify admin ───────────────────────────
    await complete_order(order_id)

    # Auto-upgrade membership tier
    new_tier = await auto_upgrade_membership(db_user["id"])
    tier_msg = ""
    if new_tier and new_tier != "none":
        from bot.config import MEMBERSHIP_TIERS
        tier_name = MEMBERSHIP_TIERS.get(new_tier, {}).get("name", new_tier)
        tier_msg = f"\n\n🎉 <b>Tier Upgraded to {tier_name}!</b>"

    # Pay referral bonus (first purchase only)
    if db_user.get("referred_by"):
        referrals = await get_referrals(db_user["referred_by"])
        my_ref = next(
            (r for r in referrals if r.get("referred_id") == db_user["id"] and not r.get("bonus_paid")),
            None,
        )
        if my_ref:
            ref_bonus = float(await _get_setting("referral_bonus") or "0.05")
            await pay_referral_bonus(db_user["referred_by"], db_user["id"], ref_bonus)
            try:
                from bot.database import get_user_by_id
                referrer = await get_user_by_id(db_user["referred_by"])
                if referrer:
                    rb = InlineKeyboardBuilder()
                    rb.row(InlineKeyboardButton(text="💰 View Wallet", callback_data="menu:wallet"))
                    await callback.bot.send_message(
                        referrer["telegram_id"],
                        f"🎉 <b>Referral Bonus!</b>\n\nYour referral made their first purchase!\nYou earned: <b>+${ref_bonus:.2f}</b>",
                        reply_markup=rb.as_markup(),
                        parse_mode="HTML",
                    )
            except Exception as e:
                logger.warning(f"Could not notify referrer: {e}")

    # ── Sales group notification ──────────────────────────────────────────────
    try:
        tg = callback.from_user
        # Mask display name: first letter + asterisks
        raw_name = tg.username or tg.first_name or "User"
        masked = raw_name[0].upper() + "*" * max(4, len(raw_name) - 1)
        logo = product.get("logo") or ""
        qty_str = f"{qty}×" if qty > 1 else "1×"
        group_text = f"🔥 User <b>{masked}</b> just bought {qty_str} {logo} <b>{product['name']}</b>!"
        deep_link = f"https://t.me/{BOT_USERNAME}?start=prod_{product_id}"
        group_kb = InlineKeyboardBuilder()
        group_kb.row(InlineKeyboardButton(
            text=f"🛒 Get {product['name']}",
            url=deep_link,
        ))
        await callback.bot.send_message(
            SALES_GROUP_ID,
            group_text,
            reply_markup=group_kb.as_markup(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Could not send group sale notification: {e}")

    # ── Notify admin ─────────────────────────────────────────────────────────
    tg = callback.from_user
    uname = f"@{tg.username}" if tg.username else f"[{tg.id}]"
    user_info = f"👤 {tg.first_name or 'N/A'} {uname} — ID: <code>{tg.id}</code>"
    qty_line = f"\nQuantity: <b>{qty}x</b>" if qty > 1 else ""
    admin_text = (
        f"🛒 <b>New Order #{order_id}!</b>\n\n"
        f"From: {user_info}\n"
        f"Product: <b>{product['name']}</b>"
        f"{qty_line}\n"
        f"Amount: <b>${final_price:.2f}</b>\n\n"
        f"⚠️ <b>Deliver manually!</b>"
    )
    admin_kb = InlineKeyboardBuilder()
    admin_kb.row(InlineKeyboardButton(text="📦 Manual Delivery", callback_data="admin:manual_delivery"))
    for admin_id in ADMIN_IDS:
        try:
            await callback.bot.send_message(admin_id, admin_text, reply_markup=admin_kb.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")

    # ── Reply to user ─────────────────────────────────────────────────────────
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📧 Send Email for Delivery",
        callback_data=f"shop:send_email:{order_id}",
    ))
    builder.row(
        InlineKeyboardButton(text="🛍️ Shop Again", callback_data="menu:shop"),
        InlineKeyboardButton(text="🏠 Menu", callback_data="menu:main"),
    )
    builder.row(InlineKeyboardButton(text="🆘 Support", callback_data="menu:support"))
    qty_display = f"  ×{qty}" if qty > 1 else ""
    await callback.message.edit_text(
        f"✅ <b>Order Placed! #{order_id}</b>\n\n"
        f"Product: <b>{product['name']}{qty_display}</b>\n"
        f"Paid: <b>${final_price:.2f}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ Your credentials will be delivered to this chat <b>shortly</b>.\n\n"
        f"📧 Tap <b>Send Email for Delivery</b> if you need delivery to your email.\n\n"
        f"If you don't receive within 24 hours, contact support."
        f"{tier_msg}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer("✅ Order placed!")


# ── Email delivery request ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("shop:send_email:"))
async def cb_send_email(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split(":")[2])
    await state.set_state(ShopStates.delivery_email)
    await state.update_data(email_order_id=order_id)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main"))
    await callback.message.edit_text(
        "📧 <b>Email for Delivery</b>\n\n"
        "Type your <b>email address</b> below and send it.\n"
        "We'll deliver your product to that email:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ShopStates.delivery_email)
async def cb_delivery_email(message: Message, state: FSMContext, db_user: dict):
    import re
    email = message.text.strip() if message.text else ""
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        await message.answer(
            "❌ That doesn't look like a valid email. Please try again (e.g. <code>you@gmail.com</code>).",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    order_id = data.get("email_order_id", "?")
    await state.clear()

    tg = message.from_user
    uname = f"@{tg.username}" if tg.username else f"[{tg.id}]"

    # Notify admins
    admin_text = (
        f"📧 <b>Email Delivery Request</b>\n\n"
        f"🧾 Order: <b>#{order_id}</b>\n"
        f"👤 User: {tg.first_name or 'N/A'} {uname}\n"
        f"🆔 ID: <code>{tg.id}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📮 <b>Delivery Email:</b>\n"
        f"<code>{email}</code>"
    )
    admin_kb = InlineKeyboardBuilder()
    admin_kb.row(InlineKeyboardButton(
        text="✅ Mark as Delivered",
        callback_data=f"admin:email_done:{order_id}:{tg.id}",
    ))
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id, admin_text,
                reply_markup=admin_kb.as_markup(),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Could not send email request to admin {admin_id}: {e}")

    # Confirm to user
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛍️ Shop", callback_data="menu:shop"),
        InlineKeyboardButton(text="🏠 Menu", callback_data="menu:main"),
    )
    await message.answer(
        f"✅ <b>Email Submitted!</b>\n\n"
        f"📮 <code>{email}</code>\n\n"
        f"Order <b>#{order_id}</b> will be delivered to this address shortly.\n"
        f"You'll get a confirmation here once it's done.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
