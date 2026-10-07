"""Extra admin panels: Binance auto-pay, Force Join, custom menu buttons and
premium emoji management.

Kept in its own module so the original `admin.py` stays untouched and easy to
merge/update. Registered right after `admin.router` in `bot/main.py`.
"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import ADMIN_IDS, BINANCE_API_KEY, BINANCE_API_SECRET
from bot.database import (
    add_custom_menu_button,
    delete_custom_menu_button,
    get_binance_payments,
    get_custom_menu_buttons,
    get_force_join_config,
    get_premium_emoji_ids,
    get_setting,
    set_force_join_channels,
    set_force_join_enabled,
    set_premium_emoji_id,
    set_setting,
)
from bot.keyboards.menus import (
    admin_binance_kb,
    admin_force_join_kb,
    admin_menu_buttons_kb,
    admin_premium_emoji_kb,
    cancel_kb,
)
from bot.utils.binance import test_credentials
from bot.utils.ui import DIVIDER, PREMIUM_EMOJI, pe, refresh_premium_emoji, sky

router = Router()
logger = logging.getLogger(__name__)


def is_admin(tg_id: int) -> bool:
    return tg_id in ADMIN_IDS


async def _check_admin(callback: CallbackQuery) -> bool:
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Access denied.", show_alert=True)
        return False
    return True


class ExtraStates(StatesGroup):
    binance_window = State()
    force_join_channel = State()
    menu_btn_label = State()
    menu_btn_type = State()
    menu_btn_value = State()
    pe_name = State()
    pe_id = State()


# ─── BINANCE AUTO PAYMENT ────────────────────────────────────────────────────

async def _binance_screen():
    enabled = (await get_setting("binance_auto_enabled")) == "1"
    amount_only = (await get_setting("binance_amount_only")) == "1"
    window = int((await get_setting("binance_window_hours")) or 24)
    configured = bool(BINANCE_API_KEY and BINANCE_API_SECRET)
    text = (
        f"{pe('money')} <b>BINANCE AUTO PAYMENT</b>\n"
        f"{DIVIDER}\n"
        f"{pe('check') if configured else pe('cross')} API Key: "
        f"<b>{'configured (read-only)' if configured else 'missing'}</b>\n"
        f"{pe('bolt')} Auto detect: <b>{'ON' if enabled else 'OFF'}</b>\n"
        f"{pe('chart')} Amount-only match: <b>{'ON' if amount_only else 'OFF'}</b>\n"
        f"{pe('clock')} Time window: <b>{window} hours</b>\n"
        f"{DIVIDER}\n"
        f"Users submit their Binance <b>Order ID</b> and the bot verifies it by "
        f"<b>order id + amount + time</b> automatically."
    )
    return text, admin_binance_kb(enabled, amount_only, window, configured)


@router.callback_query(F.data == "admin:binance_settings")
async def cb_binance_settings(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.clear()
    text, kb = await _binance_screen()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:binance_toggle")
async def cb_binance_toggle(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    current = (await get_setting("binance_auto_enabled")) == "1"
    await set_setting("binance_auto_enabled", "0" if current else "1")
    text, kb = await _binance_screen()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Auto pay " + ("disabled" if current else "enabled"))


@router.callback_query(F.data == "admin:binance_toggle_amount")
async def cb_binance_toggle_amount(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    current = (await get_setting("binance_amount_only")) == "1"
    await set_setting("binance_amount_only", "0" if current else "1")
    text, kb = await _binance_screen()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Updated")


@router.callback_query(F.data == "admin:binance_window")
async def cb_binance_window(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(ExtraStates.binance_window)
    await callback.message.edit_text(
        f"{pe('clock')} <b>Time Window</b>\n{DIVIDER}\n"
        f"Send how many <b>hours</b> back the bot should search Binance history "
        f"(1 – 168):",
        reply_markup=cancel_kb("admin:binance_settings"), parse_mode="HTML",
    )
    await callback.answer()


@router.message(ExtraStates.binance_window)
async def process_binance_window(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        hours = int((message.text or "").strip())
        if not 1 <= hours <= 168:
            raise ValueError
    except ValueError:
        await message.answer("❌ Send a whole number between 1 and 168.")
        return
    await state.clear()
    await set_setting("binance_window_hours", str(hours))
    text, kb = await _binance_screen()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin:binance_test")
async def cb_binance_test(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    await callback.answer("Testing…")
    result = await test_credentials(BINANCE_API_KEY, BINANCE_API_SECRET)
    if result["ok"]:
        msg = f"{pe('check')} <b>Binance API connection OK</b> (read-only key working)."
    else:
        msg = f"{pe('cross')} <b>Binance API failed</b>\n<code>{result['error']}</code>"
    await callback.message.answer(msg, reply_markup=cancel_kb("admin:binance_settings"),
                                  parse_mode="HTML")


@router.callback_query(F.data == "admin:binance_log")
async def cb_binance_log(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    rows = await get_binance_payments(20)
    if not rows:
        await callback.answer("No verified Binance payments yet.", show_alert=True)
        return
    lines = [f"{pe('chart')} <b>LAST VERIFIED PAYMENTS</b>", DIVIDER]
    for r in rows:
        lines.append(
            f"<code>{r['order_id']}</code> — ${r['amount']:.2f} "
            f"• {r.get('username') or r.get('user_id')} • {r.get('created_at', '')[:16]}"
        )
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=cancel_kb("admin:binance_settings"), parse_mode="HTML"
    )
    await callback.answer()


# ─── FORCE CHANNEL JOIN ──────────────────────────────────────────────────────

async def _force_join_screen():
    config = await get_force_join_config()
    listed = "\n".join(f"• {c}" for c in config["channels"]) or "<i>No channels added yet.</i>"
    text = (
        f"{pe('lock')} <b>FORCE CHANNEL JOIN</b>\n"
        f"{DIVIDER}\n"
        f"Status: <b>{'ON 🟢' if config['enabled'] else 'OFF 🔴'}</b>\n\n"
        f"<b>Required channels:</b>\n{listed}\n\n"
        f"{DIVIDER}\n"
        f"{pe('warning')} The bot must be an <b>admin</b> in each channel so it can "
        f"check membership. Admins are never blocked."
    )
    return text, admin_force_join_kb(config["enabled"], config["channels"])


@router.callback_query(F.data == "admin:force_join")
async def cb_force_join(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.clear()
    text, kb = await _force_join_screen()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:force_join_toggle")
async def cb_force_join_toggle(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    config = await get_force_join_config()
    if not config["enabled"] and not config["channels"]:
        await callback.answer("Add at least one channel first.", show_alert=True)
        return
    await set_force_join_enabled(not config["enabled"])
    text, kb = await _force_join_screen()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Force join " + ("disabled" if config["enabled"] else "enabled"))


@router.callback_query(F.data == "admin:force_join_add")
async def cb_force_join_add(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(ExtraStates.force_join_channel)
    await callback.message.edit_text(
        f"{pe('megaphone')} <b>Add Channel</b>\n{DIVIDER}\n"
        f"Send the channel username, e.g. <code>@mychannel</code>\n"
        f"(the bot must be an admin there)",
        reply_markup=cancel_kb("admin:force_join"), parse_mode="HTML",
    )
    await callback.answer()


@router.message(ExtraStates.force_join_channel)
async def process_force_join_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    channel = (message.text or "").strip()
    if not channel:
        await message.answer("❌ Empty. Send a channel username like @mychannel.")
        return
    if not channel.startswith("@") and not channel.startswith("http"):
        channel = "@" + channel.lstrip("@")
    await state.clear()
    config = await get_force_join_config()
    channels = config["channels"]
    if channel not in channels:
        channels.append(channel)
        await set_force_join_channels(channels)
    text, kb = await _force_join_screen()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:force_join_del:"))
async def cb_force_join_del(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    index = int(callback.data.split(":")[2])
    config = await get_force_join_config()
    channels = config["channels"]
    if 0 <= index < len(channels):
        channels.pop(index)
        await set_force_join_channels(channels)
        if not channels:
            await set_force_join_enabled(False)
    text, kb = await _force_join_screen()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Removed")


# ─── CUSTOM MAIN-MENU BUTTONS ────────────────────────────────────────────────

async def _menu_buttons_screen():
    buttons = await get_custom_menu_buttons()
    listed = "\n".join(
        f"{i + 1}. <b>{b.get('label')}</b> — "
        f"{'link' if b.get('type') == 'url' else 'text popup'}"
        for i, b in enumerate(buttons)
    ) or "<i>No custom buttons yet.</i>"
    text = (
        f"{pe('sparkles')} <b>MAIN MENU BUTTONS</b>\n"
        f"{DIVIDER}\n"
        f"Add or remove extra buttons that appear under the main menu when a "
        f"user starts the bot.\n\n{listed}"
    )
    return text, admin_menu_buttons_kb(buttons)


@router.callback_query(F.data == "admin:menu_buttons")
async def cb_menu_buttons(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.clear()
    text, kb = await _menu_buttons_screen()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:menu_btn_add")
async def cb_menu_btn_add(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(ExtraStates.menu_btn_label)
    await callback.message.edit_text(
        f"{pe('sparkles')} <b>New Menu Button (1/3)</b>\n{DIVIDER}\n"
        f"Send the button <b>label</b> (emoji allowed), e.g. <code>📕 Rules</code>",
        reply_markup=cancel_kb("admin:menu_buttons"), parse_mode="HTML",
    )
    await callback.answer()


@router.message(ExtraStates.menu_btn_label)
async def process_menu_btn_label(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    label = (message.text or "").strip()
    if not label:
        await message.answer("❌ Empty label.")
        return
    await state.update_data(label=label)
    await state.set_state(ExtraStates.menu_btn_value)
    await message.answer(
        f"{pe('link')} <b>New Menu Button (2/3)</b>\n{DIVIDER}\n"
        f"Now send either:\n"
        f"• a <b>link</b> (starting with http) — opens the URL, or\n"
        f"• any <b>text</b> — shown to the user when tapped.",
        reply_markup=cancel_kb("admin:menu_buttons"), parse_mode="HTML",
    )


@router.message(ExtraStates.menu_btn_value)
async def process_menu_btn_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    value = (message.text or "").strip()
    if not value:
        await message.answer("❌ Empty value.")
        return
    data = await state.get_data()
    await state.clear()
    btype = "url" if value.lower().startswith("http") else "text"
    await add_custom_menu_button(data["label"], btype, value, "primary")
    text, kb = await _menu_buttons_screen()
    await message.answer(f"{pe('check')} Button added.", parse_mode="HTML")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:menu_btn_del:"))
async def cb_menu_btn_del(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    await delete_custom_menu_button(int(callback.data.split(":")[2]))
    text, kb = await _menu_buttons_screen()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Removed")


# ─── PREMIUM EMOJI ───────────────────────────────────────────────────────────

async def _premium_emoji_screen():
    mapping = await get_premium_emoji_ids()
    names = ", ".join(f"<code>{n}</code>" for n in PREMIUM_EMOJI)
    text = (
        f"{pe('crown')} <b>PREMIUM EMOJI</b>\n"
        f"{DIVIDER}\n"
        f"Map any slot to a Telegram <b>custom (premium) emoji ID</b>. "
        f"The bot renders it as <code>&lt;tg-emoji&gt;</code> and falls back to the "
        f"normal emoji for users without Premium.\n\n"
        f"<b>Configured:</b> {len(mapping)}\n\n"
        f"<b>Slots:</b> {names}\n\n"
        f"{pe('bolt')} Tip: forward a premium emoji to @idstickerbot (or any "
        f"custom-emoji ID bot) to get its ID."
    )
    return text, admin_premium_emoji_kb(mapping)


@router.callback_query(F.data == "admin:premium_emoji")
async def cb_premium_emoji(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.clear()
    text, kb = await _premium_emoji_screen()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:pe_add")
async def cb_pe_add(callback: CallbackQuery, state: FSMContext):
    if not await _check_admin(callback):
        return
    await state.set_state(ExtraStates.pe_name)
    await callback.message.edit_text(
        f"{pe('crown')} <b>Set Premium Emoji (1/2)</b>\n{DIVIDER}\n"
        f"Send the <b>slot name</b> (e.g. <code>fire</code>, <code>cart</code>, "
        f"<code>crown</code>):",
        reply_markup=cancel_kb("admin:premium_emoji"), parse_mode="HTML",
    )
    await callback.answer()


@router.message(ExtraStates.pe_name)
async def process_pe_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    name = (message.text or "").strip().lower()
    if name not in PREMIUM_EMOJI:
        await message.answer(
            "❌ Unknown slot. Valid slots:\n"
            + ", ".join(PREMIUM_EMOJI)
        )
        return
    await state.update_data(pe_name=name)
    await state.set_state(ExtraStates.pe_id)
    await message.answer(
        f"{pe('crown')} <b>Set Premium Emoji (2/2)</b>\n{DIVIDER}\n"
        f"Now send the <b>custom emoji ID</b> for <code>{name}</code> "
        f"(a long number), or send a message containing the premium emoji itself.",
        reply_markup=cancel_kb("admin:premium_emoji"), parse_mode="HTML",
    )


@router.message(ExtraStates.pe_id)
async def process_pe_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    emoji_id = (message.text or "").strip()
    # If the admin simply sent the premium emoji, read its ID from the entities.
    for entity in (message.entities or []):
        if entity.type == "custom_emoji" and entity.custom_emoji_id:
            emoji_id = entity.custom_emoji_id
            break
    if not emoji_id.isdigit():
        await message.answer("❌ Send a numeric custom emoji ID, or the premium emoji itself.")
        return
    data = await state.get_data()
    await state.clear()
    await set_premium_emoji_id(data["pe_name"], emoji_id)
    await refresh_premium_emoji()
    text, kb = await _premium_emoji_screen()
    await message.answer(
        f"{pe('check')} Saved — preview: {pe(data['pe_name'])}", parse_mode="HTML"
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin:pe_del:"))
async def cb_pe_del(callback: CallbackQuery):
    if not await _check_admin(callback):
        return
    name = callback.data.split(":", 2)[2]
    await set_premium_emoji_id(name, "")
    await refresh_premium_emoji()
    text, kb = await _premium_emoji_screen()
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Removed")
