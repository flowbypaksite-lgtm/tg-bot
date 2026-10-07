from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict, Any

from bot.utils.ui import btn, green, red, sky, stock_btn, pe

# Colour rules used across the whole bot:
#   green (success) -> in stock / positive / confirm
#   red   (danger)  -> out of stock / destructive / cancel-negative
#   sky   (primary) -> navigation: Back / Main Menu / Cancel


def main_menu_kb(custom_buttons: List[Dict[str, Any]] = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Row 1: Shop (full width)
    builder.row(green(f"{pe('shop')} Shop", callback_data="menu:shop"))
    # Row 2: Wallet | Deposit
    builder.row(
        green(f"{pe('wallet')} Wallet", callback_data="menu:wallet"),
        green(f"{pe('card')} Deposit", callback_data="menu:deposit_info"),
    )
    # Row 3: Profile | Freebies
    builder.row(
        sky(f"{pe('user')} Profile", callback_data="menu:profile"),
        green(f"{pe('gift')} Freebies", callback_data="menu:freebies"),
    )
    # Row 4: Referral | Membership
    builder.row(
        sky(f"{pe('link')} Referral", callback_data="menu:referral"),
        sky(f"{pe('crown')} Membership", callback_data="menu:membership"),
    )
    # Row 5: Support (full width)
    builder.row(sky(f"{pe('support')} Support", callback_data="menu:support"))
    # Row 6+: Admin-defined custom buttons
    for i, b in enumerate(custom_buttons or []):
        label = b.get("label", "Button")
        style = b.get("style", "primary")
        if b.get("type") == "url":
            builder.row(btn(label, style, url=b.get("value", "https://t.me")))
        else:
            builder.row(btn(label, style, callback_data=f"menu:custom:{i}"))
    # Last row: Join Channel (URL)
    builder.row(sky(f"{pe('megaphone')} Join Channel", url="https://t.me/paktoolsofficial"))
    return builder.as_markup()


def admin_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats"),
        InlineKeyboardButton(text="📦 Products", callback_data="admin:products"),
    )
    builder.row(
        InlineKeyboardButton(text="🔍 Search User", callback_data="admin:search_user"),
        InlineKeyboardButton(text="📋 Orders", callback_data="admin:orders"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Add Balance", callback_data="admin:quick_add"),
        InlineKeyboardButton(text="➖ Remove Balance", callback_data="admin:quick_remove"),
    )
    builder.row(
        InlineKeyboardButton(text="📦 Manual Delivery", callback_data="admin:manual_delivery"),
        InlineKeyboardButton(text="🎁 Redeem Codes", callback_data="admin:redeem_codes"),
    )
    builder.row(
        InlineKeyboardButton(text="💳 Pending Deposits", callback_data="admin:deposits"),
        InlineKeyboardButton(text="📢 Broadcast", callback_data="admin:broadcast"),
    )
    builder.row(
        InlineKeyboardButton(text="📣 Product Alert", callback_data="admin:product_broadcast"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Payment Settings", callback_data="admin:payment_settings"),
        InlineKeyboardButton(text="🔗 Referral Settings", callback_data="admin:referral_settings"),
    )
    builder.row(
        InlineKeyboardButton(text="🔔 Low Stock Threshold", callback_data="admin:low_stock_settings"),
    )
    builder.row(
        green(text="🟡 Binance Auto Pay", callback_data="admin:binance_settings"),
        InlineKeyboardButton(text="🔒 Force Join", callback_data="admin:force_join"),
    )
    builder.row(
        InlineKeyboardButton(text="🧩 Menu Buttons", callback_data="admin:menu_buttons"),
        InlineKeyboardButton(text="✨ Premium Emoji", callback_data="admin:premium_emoji"),
    )
    builder.row(sky(text="🏠 Back to Menu", callback_data="menu:main"))
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(sky(f"{pe('home')} Main Menu", callback_data="menu:main"))
    return builder.as_markup()


def back_button(callback: str = "menu:main") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(sky(f"{pe('back')} Back", callback_data=callback))
    return builder.as_markup()


# ─── SHOP ────────────────────────────────────────────────────────────────────

def shop_products_kb(products: List[Dict]) -> InlineKeyboardMarkup:
    """Product list. Green button = in stock, red button = out of stock."""
    builder = InlineKeyboardBuilder()
    for p in products:
        in_stock = (p.get("stock_count", 0) or 0) > 0
        price_str = "FREE" if p.get("price", 1) == 0.0 else f"${p['price']:.2f}"
        icon = p.get("logo") or ("🟢" if in_stock else "🔴")
        tail = price_str if in_stock else "SOLD OUT"
        label = f"{icon} {p['name']}  —  {tail}"
        builder.row(stock_btn(label, in_stock, callback_data=f"shop:prod:{p['id']}"))
    builder.row(sky("🏠 Main Menu", callback_data="menu:main"))
    return builder.as_markup()


PRESET_QTYS = [1, 2, 3, 5, 10, 15, 20, 25]


def product_detail_kb(
    product_id: int,
    qty: int = 1,
    unit_price: float = 0.0,
    is_free: bool = False,
    has_alert: bool = False,
    custom_buttons: list = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_free:
        builder.row(green("🎟️ Claim Free", callback_data=f"shop:buy:{product_id}:1"))
    else:
        # Quantity grid header label
        builder.row(InlineKeyboardButton(text="🛒  Buy Quantity:", callback_data="shop:noop"))
        # Preset qty buttons — two rows of 4
        row1 = [InlineKeyboardButton(
            text=f"✅ {q}" if q == qty else str(q),
            callback_data=f"shop:setqty:{product_id}:{q}",
        ) for q in PRESET_QTYS[:4]]
        row2 = [InlineKeyboardButton(
            text=f"✅ {q}" if q == qty else str(q),
            callback_data=f"shop:setqty:{product_id}:{q}",
        ) for q in PRESET_QTYS[4:]]
        builder.row(*row1)
        builder.row(*row2)
        # Custom quantity
        custom_label = f"✏️ Custom: {qty}" if qty not in PRESET_QTYS else "✏️ Custom Quantity"
        builder.row(InlineKeyboardButton(text=custom_label, callback_data=f"shop:customqty:{product_id}"))
        # Buy button
        total = round(unit_price * qty, 2)
        builder.row(green(
            f"✅ Buy {qty}x  —  ${total:.2f}",
            callback_data=f"shop:buy:{product_id}:{qty}",
        ))
    # Custom buttons (blue = URL, green = text popup)
    for i, btn in enumerate(custom_buttons or []):
        label = btn.get("label", "Button")
        btype = btn.get("type", "text")
        value = btn.get("value", "")
        if btype == "url":
            builder.row(sky(f"🔵 {label}", url=value))
        else:
            builder.row(green(f"🟢 {label}", callback_data=f"shop:cbtn:{product_id}:{i}"))
    # Alert toggle
    alert_text = "🔕 Remove Alert" if has_alert else "🔔 Set Price Alert"
    builder.row(btn(alert_text, "danger" if has_alert else "primary",
                    callback_data=f"shop:alert:{product_id}"))
    builder.row(sky("« Back to Shop", callback_data="menu:shop"))
    return builder.as_markup()


def buy_confirm_kb(product_id: int, qty: int, price: float) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        green(f"✅ Confirm (${price:.2f})", callback_data=f"shop:confirm:{product_id}:{qty}"),
        sky("❌ Cancel", callback_data=f"shop:prod:{product_id}"),
    )
    return builder.as_markup()


def checkout_payment_kb(product_id: int, qty: int, total: float) -> InlineKeyboardMarkup:
    """Payment method selector shown when user taps Buy on a paid product."""
    builder = InlineKeyboardBuilder()
    builder.row(green(
        f"{pe('wallet')} Pay from Wallet  (${total:.2f})",
        callback_data=f"shop:wallet_pay:{product_id}:{qty}",
    ))
    builder.row(green("💛 Binance Pay  ⚡ Auto", callback_data=f"shop:checkout_method:{product_id}:{qty}:binancepay"))
    builder.row(green("♦️ USDT TRC20  ⚡ Auto", callback_data=f"shop:checkout_method:{product_id}:{qty}:trc20"))
    builder.row(green("💠 USDT BEP20  ⚡ Auto", callback_data=f"shop:checkout_method:{product_id}:{qty}:bep20"))
    builder.row(btn("💳 SadaPay", "primary", callback_data=f"shop:checkout_method:{product_id}:{qty}:sadapay"))
    builder.row(btn(f"{pe('gift')} Redeem Code", "primary", callback_data=f"shop:checkout_method:{product_id}:{qty}:redeem"))
    builder.row(sky(f"{pe('back')} Back", callback_data=f"shop:prod:{product_id}"))
    return builder.as_markup()


# ─── WALLET ──────────────────────────────────────────────────────────────────

def wallet_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        green("➕ Add Balance", callback_data="wallet:deposit"),
        sky("📜 History", callback_data="wallet:history"),
    )
    builder.row(sky("🏠 Main Menu", callback_data="menu:main"))
    return builder.as_markup()


def payment_methods_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(green("💛 Binance Pay  ⚡ Auto", callback_data="wallet:method:binancepay"))
    builder.row(green("♦️ USDT TRC20  ⚡ Auto", callback_data="wallet:method:trc20"))
    builder.row(green("💠 USDT BEP20  ⚡ Auto", callback_data="wallet:method:bep20"))
    builder.row(btn("💳 SadaPay", "primary", callback_data="wallet:method:sadapay"))
    builder.row(btn(f"{pe('gift')} Redeem Code", "primary", callback_data="wallet:redeem"))
    builder.row(sky(f"{pe('back')} Back", callback_data="menu:main"))
    return builder.as_markup()


def admin_redeem_codes_kb(codes: List[Dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Create Code", callback_data="admin:redeem_create"))
    for c in codes:
        status = "✅" if c["times_used"] < c["usage_limit"] else "🔴"
        exp = f" exp:{c['expires_at'][:10]}" if c.get("expires_at") else ""
        builder.row(InlineKeyboardButton(
            text=f"{status} {c['code']} — ${c['amount']:.2f} ({c['times_used']}/{c['usage_limit']}){exp}",
            callback_data=f"admin:redeem_del:{c['id']}",
        ))
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="admin:main"))
    return builder.as_markup()


def deposit_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(sky("❌ Cancel", callback_data="wallet:deposit"))
    return builder.as_markup()


def admin_deposit_approval_kb(deposit_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        green("✅ Approve", callback_data=f"admin:approve_dep:{deposit_id}"),
        red("❌ Reject", callback_data=f"admin:reject_dep:{deposit_id}"),
    )
    return builder.as_markup()


# ─── SUPPORT ─────────────────────────────────────────────────────────────────

def support_reply_kb(user_telegram_id: int, ticket_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="↩️ Reply to User",
            callback_data=f"admin:reply:{user_telegram_id}:{ticket_id}",
        )
    )
    return builder.as_markup()


# ─── MEMBERSHIP ──────────────────────────────────────────────────────────────

def membership_kb(current_tier: str = "none") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))
    return builder.as_markup()


# ─── ADMIN — PRODUCTS ────────────────────────────────────────────────────────

def admin_products_kb(products: List[Dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Add Product", callback_data="admin:add_product"))
    for p in products:
        status = "✅" if p.get("is_active") else "❌"
        stock = p.get("stock_count", 0)
        builder.row(stock_btn(
            f"{status} {p['name']} (${p['price']:.2f}) [{stock}]",
            stock > 0,
            callback_data=f"admin:prod:{p['id']}",
        ))
    builder.row(sky("◀️ Back", callback_data="admin:main"))
    return builder.as_markup()


def admin_product_manage_kb(product_id: int, is_active: bool, has_photo: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "🔴 Deactivate" if is_active else "🟢 Activate"
    builder.row(
        InlineKeyboardButton(text="✏️ Edit Name", callback_data=f"admin:edit_name:{product_id}"),
        InlineKeyboardButton(text="📝 Edit Desc", callback_data=f"admin:edit_desc:{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="💵 Change Price", callback_data=f"admin:edit_price:{product_id}"),
        InlineKeyboardButton(text="📝 Logo Text / Emoji", callback_data=f"admin:edit_logo:{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🖼 Change Product Logo", callback_data=f"admin:upload_logo:{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🟢 Set Green", callback_data=f"admin:set_status:{product_id}:🟢"),
        InlineKeyboardButton(text="🔴 Set Red",   callback_data=f"admin:set_status:{product_id}:🔴"),
        InlineKeyboardButton(text="🔄 Auto",      callback_data=f"admin:set_status:{product_id}:auto"),
    )
    builder.row(
        InlineKeyboardButton(text="🛡 Warranty",      callback_data=f"admin:edit_warranty:{product_id}"),
        InlineKeyboardButton(text="🏷 Product Type",  callback_data=f"admin:edit_ptype:{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🚚 Delivery Type", callback_data=f"admin:edit_delivery:{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🔵 Add Blue Button", callback_data=f"admin:add_blue_btn:{product_id}"),
        InlineKeyboardButton(text="🟢 Add Green Button", callback_data=f"admin:add_green_btn:{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🗂 Manage Buttons", callback_data=f"admin:manage_btns:{product_id}"),
    )
    if has_photo:
        builder.row(
            InlineKeyboardButton(text="🗑 Remove Product Logo", callback_data=f"admin:remove_logo:{product_id}"),
        )
    builder.row(
        btn(toggle_text, "danger" if is_active else "success", callback_data=f"admin:toggle:{product_id}"),
        red("🗑️ Delete Product", callback_data=f"admin:delete_confirm:{product_id}"),
    )
    builder.row(
        green("➕ Add Stock", callback_data=f"admin:add_stock:{product_id}"),
        red("➖ Remove Stock", callback_data=f"admin:remove_stock:{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="👁️ View Stock", callback_data=f"admin:view_stock:{product_id}"),
        sky("◀️ Back", callback_data="admin:products"),
    )
    return builder.as_markup()


def admin_delete_confirm_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        red("🗑️ Yes, Delete", callback_data=f"admin:delete:{product_id}"),
        sky("❌ Cancel", callback_data=f"admin:prod:{product_id}"),
    )
    return builder.as_markup()


def admin_user_detail_kb(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    ban_text = "✅ Unban" if is_banned else "🚫 Ban"
    builder.row(
        btn(ban_text, "success" if is_banned else "danger", callback_data=f"admin:ban:{user_id}"),
        green("➕ Add Balance", callback_data=f"admin:addbal:{user_id}"),
    )
    builder.row(
        red("➖ Deduct Balance", callback_data=f"admin:deductbal:{user_id}"),
        sky("💳 Set Balance", callback_data=f"admin:setbal:{user_id}"),
    )
    builder.row(sky("◀️ Back", callback_data="admin:main"))
    return builder.as_markup()


def cancel_kb(back_callback: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(sky("❌ Cancel", callback_data=back_callback))
    return builder.as_markup()


# ─── ADMIN — NEW PANELS ──────────────────────────────────────────────────────

def admin_binance_kb(enabled: bool, amount_only: bool, window_hours: int,
                     configured: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(btn(
        "🟢 Auto Pay: ON" if enabled else "🔴 Auto Pay: OFF",
        "success" if enabled else "danger",
        callback_data="admin:binance_toggle",
    ))
    builder.row(btn(
        f"🔎 Amount-only match: {'ON' if amount_only else 'OFF'}",
        "success" if amount_only else "danger",
        callback_data="admin:binance_toggle_amount",
    ))
    builder.row(btn(f"⏱ Time Window: {window_hours}h", "primary", callback_data="admin:binance_window"))
    builder.row(btn("🧪 Test API Connection", "primary", callback_data="admin:binance_test"))
    builder.row(btn("📜 Verified Payments", "primary", callback_data="admin:binance_log"))
    builder.row(sky("◀️ Back", callback_data="admin:main"))
    return builder.as_markup()


def admin_force_join_kb(enabled: bool, channels: List[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(btn(
        "🟢 Force Join: ON" if enabled else "🔴 Force Join: OFF",
        "success" if enabled else "danger",
        callback_data="admin:force_join_toggle",
    ))
    builder.row(btn("➕ Add Channel", "success", callback_data="admin:force_join_add"))
    for i, ch in enumerate(channels):
        builder.row(red(f"🗑 {ch}", callback_data=f"admin:force_join_del:{i}"))
    builder.row(sky("◀️ Back", callback_data="admin:main"))
    return builder.as_markup()


def admin_menu_buttons_kb(buttons: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(green("➕ Add Menu Button", callback_data="admin:menu_btn_add"))
    for i, b in enumerate(buttons):
        kind = "🔗" if b.get("type") == "url" else "💬"
        builder.row(red(f"🗑 {kind} {b.get('label', '?')}", callback_data=f"admin:menu_btn_del:{i}"))
    builder.row(sky("◀️ Back", callback_data="admin:main"))
    return builder.as_markup()


def admin_premium_emoji_kb(mapping: Dict[str, str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(green("➕ Set Emoji ID", callback_data="admin:pe_add"))
    for name, eid in list(mapping.items())[:20]:
        builder.row(red(f"🗑 {name} → {eid}", callback_data=f"admin:pe_del:{name}"))
    builder.row(sky("◀️ Back", callback_data="admin:main"))
    return builder.as_markup()


def broadcast_buy_kb(product_id: int = None, bot_username: str = "",
                     extra_url: str = "") -> InlineKeyboardMarkup:
    """Keyboard attached to every broadcast — always shows a green Buy Now."""
    builder = InlineKeyboardBuilder()
    if product_id and bot_username:
        builder.row(green(f"{pe('cart')} BUY NOW",
                          url=f"https://t.me/{bot_username}?start=prod_{product_id}"))
    elif product_id:
        builder.row(green(f"{pe('cart')} BUY NOW", callback_data=f"shop:prod:{product_id}"))
    else:
        builder.row(green(f"{pe('cart')} BUY NOW", callback_data="menu:shop"))
    if extra_url:
        builder.row(sky(f"{pe('megaphone')} Channel", url=extra_url))
    return builder.as_markup()
