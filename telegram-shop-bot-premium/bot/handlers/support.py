import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from bot.keyboards.menus import support_reply_kb
from bot.database import create_support_ticket
from bot.config import ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)


class SupportStates(StatesGroup):
    waiting_message = State()


class AdminReplyStates(StatesGroup):
    waiting_reply = State()


OWNER_USERNAME = "Paktoolsstore"

def support_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✉️ Send Message to Support", callback_data="support:send"))
    builder.row(InlineKeyboardButton(text="👤 Contact Owner", url=f"https://t.me/{OWNER_USERNAME}"))
    builder.row(InlineKeyboardButton(text="📋 FAQ", callback_data="support:faq"))
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))
    return builder.as_markup()


def faq_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Back to Support", callback_data="menu:support"))
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))
    return builder.as_markup()


@router.callback_query(F.data == "menu:support")
async def cb_support(callback: CallbackQuery):
    text = (
        "🆘 <b>Support Center</b>\n\n"
        "We're here to help! Choose an option below:\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⏱ Response time: <b>Under 24 hours</b>\n"
        "🌐 Available: <b>24/7</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📌 Check the FAQ before contacting for quick answers."
    )
    await callback.message.edit_text(text, reply_markup=support_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "support:faq")
async def cb_faq(callback: CallbackQuery):
    text = (
        "📋 <b>Frequently Asked Questions</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "❓ <b>How do I get my account after purchase?</b>\n"
        "The account is delivered instantly in the chat right after payment.\n\n"
        "❓ <b>What if my account doesn't work?</b>\n"
        "Contact support within 24 hours with your Order ID and we'll replace it.\n\n"
        "❓ <b>How do I add funds to my wallet?</b>\n"
        "Go to 💰 Wallet → ➕ Add Balance and follow the payment instructions.\n\n"
        "❓ <b>How does the referral system work?</b>\n"
        "Share your personal link. When someone joins through it, you earn a bonus after their first purchase!\n\n"
        "❓ <b>What is the daily freebie?</b>\n"
        "Claim free balance every 24 hours. Maintain a streak for bigger bonuses.\n\n"
        "❓ <b>What are membership tiers?</b>\n"
        "Tiers (Bronze → Silver → Gold → Diamond) unlock automatically as you spend more. Higher tiers give bigger discounts.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Still need help? Send us a message!"
    )
    await callback.message.edit_text(text, reply_markup=faq_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "support:send")
async def cb_support_send(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SupportStates.waiting_message)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="menu:support"))
    await callback.message.edit_text(
        "✉️ <b>Contact Support</b>\n\n"
        "Type your message below. Include:\n"
        "• Your Order ID (if about a purchase)\n"
        "• A clear description of the issue\n\n"
        "We'll get back to you as soon as possible!",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SupportStates.waiting_message)
async def process_support_message(message: Message, state: FSMContext, db_user: dict):
    await state.clear()
    msg_text = message.text or "(no text)"

    # Save ticket to DB
    ticket_id = await create_support_ticket(
        user_id=db_user["id"],
        telegram_id=message.from_user.id,
        message=msg_text,
    )

    user_info = (
        f"👤 {message.from_user.first_name or 'N/A'} "
        f"(@{message.from_user.username or 'no username'}) "
        f"[ID: <code>{message.from_user.id}</code>]"
    )
    admin_text = (
        f"🆘 <b>Support Ticket #{ticket_id}</b>\n\n"
        f"From: {user_info}\n"
        f"Balance: ${db_user['balance']:.2f}\n\n"
        f"<b>Message:</b>\n<blockquote>{msg_text}</blockquote>"
    )

    reply_kb = support_reply_kb(message.from_user.id, ticket_id)

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(admin_id, admin_text, parse_mode="HTML", reply_markup=reply_kb)
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main"))
    await message.answer(
        f"✅ <b>Message Sent!</b>\n\n"
        f"Our support team received your message.\n"
        f"We'll respond within 24 hours.\n\n"
        f"<i>Ticket reference: #{ticket_id}</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


# ─── Admin reply to user ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:reply:"))
async def cb_admin_reply(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Access denied.", show_alert=True)
        return
    parts = callback.data.split(":")
    user_tg_id = int(parts[2])
    ticket_id = int(parts[3])

    await state.set_state(AdminReplyStates.waiting_reply)
    await state.update_data(user_tg_id=user_tg_id, ticket_id=ticket_id)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:main"))

    await callback.message.reply(
        f"✏️ <b>Reply to Ticket #{ticket_id}</b>\n\n"
        f"Type your reply below. It will be sent directly to the user:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminReplyStates.waiting_reply)
async def process_admin_reply(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    user_tg_id = data["user_tg_id"]
    ticket_id = data["ticket_id"]
    await state.clear()

    reply_text = message.text or "(no text)"

    try:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🆘 Contact Support Again", callback_data="support:send"))
        await message.bot.send_message(
            user_tg_id,
            f"📩 <b>Support Reply</b>\n\n"
            f"<i>Regarding ticket #{ticket_id}</i>\n\n"
            f"<blockquote>{reply_text}</blockquote>\n\n"
            f"If you have further questions, use the button below.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await message.answer(f"✅ Reply sent to user successfully!")
    except Exception as e:
        await message.answer(f"❌ Failed to send reply: {e}")
