import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from bot.keyboards.menus import (
    wallet_kb, payment_methods_kb, deposit_cancel_kb, admin_deposit_approval_kb,
)
from bot.database import (
    get_transactions, update_balance, get_user,
    create_pending_deposit, get_setting, use_redeem_code,
    get_used_binance_ids, is_binance_id_used, record_binance_payment,
)
from bot.config import ADMIN_IDS, BINANCE_API_KEY, BINANCE_API_SECRET
from bot.utils.binance import verify_payment
from bot.utils.ui import DIVIDER, green, pe, red, sky

router = Router()
logger = logging.getLogger(__name__)

TX_ICONS = {
    "deposit": "⬆️", "withdraw": "⬇️", "purchase": "🛍️",
    "refund": "↩️", "referral_bonus": "🔗", "freebie": "🎁",
    "welcome_bonus": "🎉", "membership": "👑", "admin_credit": "💎",
    "admin_deduct": "🔻", "redeem": "🎁",
}

METHOD_NAMES = {
    "sadapay":    "💳 SadaPay",
    "binancepay": "💛 Binance Pay",
    "trc20":      "♦️ USDT TRC20",
    "bep20":      "💠 USDT BEP20",
}


class DepositStates(StatesGroup):
    entering_amount = State()
    waiting_screenshot = State()
    entering_order_id = State()


BINANCE_METHODS = ("binancepay", "trc20", "bep20")


async def binance_auto_enabled() -> bool:
    """Auto-detection is only offered when it is switched on and configured."""
    return (
        (await get_setting("binance_auto_enabled")) == "1"
        and bool(BINANCE_API_KEY and BINANCE_API_SECRET)
    )


class RedeemStates(StatesGroup):
    entering_code = State()


@router.callback_query(F.data == "menu:deposit_info")
async def cb_deposit_info(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "💳 <b>Deposit</b>\n\nSelect your payment method:",
        reply_markup=payment_methods_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:wallet")
async def cb_wallet(callback: CallbackQuery, db_user: dict):
    text = (
        f"💰 <b>Your Wallet</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Balance: <b>${db_user['balance']:.2f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Add funds or view your transaction history."
    )
    await callback.message.edit_text(text, reply_markup=wallet_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "wallet:deposit")
async def cb_deposit(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "💳 <b>Deposit</b>\n\nSelect your payment method:",
        reply_markup=payment_methods_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "wallet:redeem")
async def cb_redeem_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RedeemStates.entering_code)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="menu:deposit_info"))
    await callback.message.edit_text(
        "🎁 <b>Redeem Code</b>\n\n"
        "Enter your redeem code below:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(RedeemStates.entering_code)
async def process_redeem_code(message: Message, state: FSMContext, db_user: dict):
    code = (message.text or "").strip().upper()
    if not code:
        await message.answer("❌ Please enter a valid code.")
        return

    result = await use_redeem_code(code, db_user["id"])
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))

    if result["success"]:
        await message.answer(
            f"✅ <b>Code Redeemed!</b>\n\n"
            f"Code: <code>{result['code']}</code>\n"
            f"Amount: <b>+${result['amount']:.2f}</b> added to your wallet! 🎉",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        # Notify admin
        from bot.config import ADMIN_IDS
        for admin_id in ADMIN_IDS:
            try:
                await message.bot.send_message(
                    admin_id,
                    f"🎁 <b>Code Redeemed</b>\n\n"
                    f"👤 {message.from_user.first_name or 'N/A'} "
                    f"(@{message.from_user.username or 'no username'})\n"
                    f"🆔 <code>{message.from_user.id}</code>\n"
                    f"Code: <code>{result['code']}</code>\n"
                    f"Amount: <b>${result['amount']:.2f}</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    else:
        reason_map = {
            "invalid":    "❌ <b>Invalid Redeem Code.</b>\n\nThis code does not exist.",
            "expired":    "❌ <b>Code Expired.</b>\n\nThis code is no longer valid.",
            "exhausted":  "❌ <b>Code Fully Used.</b>\n\nThis code has reached its usage limit.",
            "already_used": "❌ <b>Already Redeemed.</b>\n\nYou have already used this code.",
        }
        text = reason_map.get(result.get("reason", "invalid"), "❌ <b>Invalid Redeem Code.</b>")
        builder2 = InlineKeyboardBuilder()
        builder2.row(InlineKeyboardButton(text="🔁 Try Again", callback_data="wallet:redeem"))
        builder2.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))
        await message.answer(text, reply_markup=builder2.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("wallet:method:"))
async def cb_method_selected(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split(":")[2]
    if method not in METHOD_NAMES:
        await callback.answer("Invalid method.", show_alert=True)
        return

    await state.update_data(method=method)
    await state.set_state(DepositStates.entering_amount)

    method_name = METHOD_NAMES[method]
    text = (
        f"💵 <b>Enter Amount</b>\n\n"
        f"Method: <b>{method_name}</b>\n\n"
        f"How much would you like to deposit?\n"
        f"<i>Type the amount in USD (e.g. <code>10</code> or <code>25.50</code>)</i>"
    )
    await callback.message.edit_text(text, reply_markup=deposit_cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(DepositStates.entering_amount)
async def process_deposit_amount(message: Message, state: FSMContext, db_user: dict):
    text = (message.text or "").strip().replace("$", "")
    try:
        amount = round(float(text), 2)
        if amount < 1:
            await message.answer("❌ Minimum deposit is $1.00. Please enter a valid amount.")
            return
    except ValueError:
        await message.answer("❌ Invalid amount. Please enter a number like <code>10</code> or <code>25.50</code>.", parse_mode="HTML")
        return

    data = await state.get_data()
    method = data["method"]
    method_name = METHOD_NAMES[method]

    # Get payment details from settings
    if method == "sadapay":
        payment_detail = await get_setting("sadapay_number")
        instructions = (
            f"💳 <b>SadaPay Payment Instructions</b>\n\n"
            f"Send <b>${amount:.2f}</b> to:\n\n"
            f"📱 <b>SadaPay Number:</b>\n"
            f"<code>{payment_detail}</code>\n\n"
            f"⚠️ <b>Important:</b> Send exactly ${amount:.2f}\n"
            f"After sending, take a screenshot of your payment confirmation."
        )
    elif method == "binancepay":
        payment_detail = await get_setting("binance_pay_id")
        instructions = (
            f"💛 <b>Binance Pay Instructions</b>\n\n"
            f"Send <b>${amount:.2f} USDT</b> via Binance Pay to:\n\n"
            f"🆔 <b>Binance Pay ID:</b>\n"
            f"<code>{payment_detail}</code>\n\n"
            f"⚠️ <b>Use Binance Pay only — not a wallet address!</b>\n"
            f"Open Binance app → Pay → Send → enter the ID above.\n"
            f"After sending, take a screenshot of your payment confirmation."
        )
    elif method == "trc20":
        payment_detail = await get_setting("binance_trc20")
        instructions = (
            f"₿ <b>Binance TRC20 Payment Instructions</b>\n\n"
            f"Send <b>${amount:.2f} USDT</b> (TRC20 network) to:\n\n"
            f"📋 <b>Wallet Address:</b>\n"
            f"<code>{payment_detail}</code>\n\n"
            f"⚠️ <b>Use TRC20 network only!</b>\n"
            f"After sending, take a screenshot of your transaction."
        )
    else:
        payment_detail = await get_setting("binance_bep20")
        instructions = (
            f"₿ <b>Binance BEP20 Payment Instructions</b>\n\n"
            f"Send <b>${amount:.2f} USDT</b> (BEP20 / BSC network) to:\n\n"
            f"📋 <b>Wallet Address:</b>\n"
            f"<code>{payment_detail}</code>\n\n"
            f"⚠️ <b>Use BEP20 / BSC network only!</b>\n"
            f"After sending, take a screenshot of your transaction."
        )

    await state.update_data(amount=amount)
    await state.set_state(DepositStates.waiting_screenshot)

    builder = InlineKeyboardBuilder()
    auto = method in BINANCE_METHODS and await binance_auto_enabled()
    if auto:
        builder.row(green(f"{pe('bolt')} Auto Verify (Order ID)",
                          callback_data="wallet:auto_verify"))
    builder.row(sky("📸 Send Screenshot", callback_data="wallet:manual_proof"))
    builder.row(red("❌ Cancel", callback_data="menu:wallet"))

    tail = (
        f"\n\n{DIVIDER}\n"
        f"{pe('bolt')} <b>INSTANT:</b> tap <b>Auto Verify</b> and send your Binance "
        f"<b>Order ID / TxID</b> — balance is added automatically.\n"
        f"📸 Or send a screenshot for manual approval."
        if auto else "\n\n📸 <b>Send your payment screenshot below:</b>"
    )

    await message.answer(
        instructions + tail,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "wallet:manual_proof")
async def cb_manual_proof(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DepositStates.waiting_screenshot)
    await callback.answer("📸 Send the screenshot now.", show_alert=False)


@router.callback_query(F.data == "wallet:auto_verify")
async def cb_auto_verify(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("amount"):
        await callback.answer("Start the deposit again please.", show_alert=True)
        return
    await state.set_state(DepositStates.entering_order_id)
    builder = InlineKeyboardBuilder()
    builder.row(sky("📸 Send Screenshot Instead", callback_data="wallet:manual_proof"))
    builder.row(red("❌ Cancel", callback_data="menu:wallet"))
    await callback.message.answer(
        f"{pe('bolt')} <b>AUTO PAYMENT VERIFICATION</b>\n"
        f"{DIVIDER}\n"
        f"Send your Binance <b>Order ID</b> (Binance Pay) or the "
        f"<b>Transaction ID / TxID</b> of your USDT transfer.\n\n"
        f"{pe('shield')} We check the <b>order id</b>, the <b>amount</b> "
        f"(${data['amount']:.2f}) and the <b>time</b> — all read-only.",
        reply_markup=builder.as_markup(), parse_mode="HTML",
    )
    await callback.answer()


FAIL_REASONS = {
    "not_found": "No matching payment found yet. Wait ~1 minute after paying and try again.",
    "amount_mismatch": "A payment was found but the amount does not match.",
    "already_used": "This Order ID has already been used.",
    "too_old": "That payment is outside the allowed time window.",
    "outgoing": "That transaction is outgoing, not a payment to us.",
    "wrong_currency": "Only USDT / stablecoin payments are accepted.",
    "no_transactions": "No recent transactions found on our side yet.",
    "not_configured": "Auto verification is not configured. Please send a screenshot.",
}


@router.message(DepositStates.entering_order_id)
async def process_order_id(message: Message, state: FSMContext, db_user: dict):
    order_id = (message.text or "").strip()
    if not order_id or len(order_id) < 6:
        await message.answer("❌ Send a valid Binance Order ID / TxID.")
        return

    data = await state.get_data()
    amount = data.get("amount", 0.0)
    method = data.get("method", "binancepay")

    if await is_binance_id_used(order_id):
        await message.answer("❌ This Order ID has already been used.")
        return

    status = await message.answer(f"{pe('clock')} Checking Binance…", parse_mode="HTML")
    window = int((await get_setting("binance_window_hours")) or 24)
    amount_only = (await get_setting("binance_amount_only")) == "1"
    used = set(await get_used_binance_ids())

    try:
        match = await verify_payment(
            BINANCE_API_KEY, BINANCE_API_SECRET, order_id, amount,
            window_hours=window, used_ids=used, allow_amount_only=amount_only,
        )
    except Exception as exc:
        logger.exception("Binance verification failed")
        match = None

    builder = InlineKeyboardBuilder()

    if match is None:
        builder.row(sky("📸 Send Screenshot Instead", callback_data="wallet:manual_proof"))
        await state.set_state(DepositStates.waiting_screenshot)
        await status.edit_text(
            f"{pe('warning')} Could not reach Binance right now. "
            f"Please send a screenshot for manual approval.",
            reply_markup=builder.as_markup(), parse_mode="HTML",
        )
        return

    if not match.ok:
        builder.row(green(f"{pe('bolt')} Try Again", callback_data="wallet:auto_verify"))
        builder.row(sky("📸 Send Screenshot Instead", callback_data="wallet:manual_proof"))
        builder.row(red("❌ Cancel", callback_data="menu:wallet"))
        await status.edit_text(
            f"{pe('cross')} <b>Payment not verified</b>\n{DIVIDER}\n"
            f"{FAIL_REASONS.get(match.reason, 'Payment could not be verified.')}",
            reply_markup=builder.as_markup(), parse_mode="HTML",
        )
        return

    await state.clear()
    credited = round(match.amount or amount, 2)
    await update_balance(db_user["id"], credited, "deposit",
                         f"Binance auto deposit ({match.order_id})")
    await record_binance_payment(
        order_id=match.order_id, user_id=db_user["id"],
        telegram_id=message.from_user.id, amount=credited,
        currency=match.currency or "USDT", source=match.source or method,
        purpose="deposit",
    )

    user = await get_user(message.from_user.id)
    builder.row(green(f"{pe('cart')} Shop Now", callback_data="menu:shop"))
    builder.row(sky("🏠 Main Menu", callback_data="menu:main"))
    await status.edit_text(
        f"{pe('check')} <b>PAYMENT VERIFIED</b> {pe('sparkles')}\n"
        f"{DIVIDER}\n"
        f"{pe('money')} Credited: <b>${credited:.2f}</b>\n"
        f"🧾 Order ID: <code>{match.order_id}</code>\n"
        f"{pe('wallet')} New balance: <b>${(user or db_user)['balance']:.2f}</b>\n"
        f"{DIVIDER}\n"
        f"{pe('bolt')} Instantly added — enjoy your shopping!",
        reply_markup=builder.as_markup(), parse_mode="HTML",
    )

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f"{pe('check')} <b>Binance auto-deposit</b>\n"
                f"👤 @{message.from_user.username or message.from_user.id}\n"
                f"💵 ${credited:.2f} • <code>{match.order_id}</code> • {match.source}",
                parse_mode="HTML",
            )
        except Exception:
            pass


@router.message(DepositStates.waiting_screenshot)
async def process_screenshot(message: Message, state: FSMContext, db_user: dict):
    # Accept photo or document
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id
    else:
        await message.answer(
            "📸 Please send a <b>screenshot / photo</b> of your payment confirmation.",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    amount = data["amount"]
    method = data["method"]
    method_name = METHOD_NAMES[method]
    await state.clear()

    # Create pending deposit
    deposit_id = await create_pending_deposit(
        user_id=db_user["id"],
        telegram_id=message.from_user.id,
        amount=amount,
        method=method,
        screenshot_file_id=file_id,
    )

    # Notify admins
    admin_text = (
        f"💰 <b>New Deposit Request #{deposit_id}</b>\n\n"
        f"👤 <b>Name:</b> {message.from_user.first_name or 'N/A'}\n"
        f"🔖 <b>Username:</b> @{message.from_user.username or 'no username'}\n"
        f"🆔 <b>Telegram ID:</b> <code>{message.from_user.id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Amount:</b> ${amount:.2f}\n"
        f"💳 <b>Method:</b> {method_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Review the screenshot and approve or reject below.</i>"
    )
    approval_kb = admin_deposit_approval_kb(deposit_id)

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_photo(
                admin_id,
                photo=file_id,
                caption=admin_text,
                reply_markup=approval_kb,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")

    # Confirm to user
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))
    await message.answer(
        f"✅ <b>Deposit Request Submitted!</b>\n\n"
        f"Amount: <b>${amount:.2f}</b>\n"
        f"Method: <b>{method_name}</b>\n"
        f"Reference: <b>#{deposit_id}</b>\n\n"
        f"⏳ An admin will review your payment shortly.\n"
        f"You'll be notified once it's approved.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "wallet:history")
async def cb_history(callback: CallbackQuery, db_user: dict):
    transactions = await get_transactions(db_user["id"], limit=15)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="menu:wallet"))

    if not transactions:
        await callback.message.edit_text(
            "📜 <b>Transaction History</b>\n\nNo transactions yet.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    lines = []
    for tx in transactions:
        icon = TX_ICONS.get(tx["type"], "💫")
        amt = tx["amount"]
        sign = "+" if amt > 0 else ""
        date = str(tx.get("created_at", ""))[:10]
        desc = tx.get("description") or tx["type"]
        lines.append(f"{icon} <b>{sign}${abs(amt):.2f}</b> — {desc} <i>({date})</i>")

    text = f"📜 <b>Transaction History</b>\n\nLast {len(transactions)} transactions:\n\n" + "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()
