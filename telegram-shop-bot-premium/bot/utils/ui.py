"""Premium UI helpers — colored inline buttons + Telegram premium (custom) emoji.

Button colors
-------------
Telegram supports a ``style`` field on keyboard buttons with three predefined
values:

    primary  -> blue   (navigation / neutral, e.g. Back, Cancel, Menu)
    success  -> green  (positive, e.g. in-stock products, Buy, Confirm)
    danger   -> red    (negative, e.g. out of stock, Delete, Reject)

Older Telegram clients / aiogram builds simply ignore the extra field, so the
helper degrades gracefully instead of crashing.

Premium emoji
-------------
Telegram premium (custom) emoji are sent with the HTML tag::

    <tg-emoji emoji-id="5368324170671202286">🔥</tg-emoji>

Custom emoji IDs are configurable at runtime (admin panel -> Premium Emoji),
and every helper falls back to the plain unicode emoji when no ID is set, so
messages always render correctly.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from aiogram.types import InlineKeyboardButton

# ── Button styles ────────────────────────────────────────────────────────────

PRIMARY = "primary"   # blue
SUCCESS = "success"   # green
DANGER = "danger"     # red

_STYLE_SUPPORTED: Optional[bool] = None


def btn(text: str, style: Optional[str] = None, **kwargs: Any) -> InlineKeyboardButton:
    """Build an InlineKeyboardButton with an optional color *style*."""
    global _STYLE_SUPPORTED
    if not style:
        return InlineKeyboardButton(text=text, **kwargs)
    if _STYLE_SUPPORTED is False:
        return InlineKeyboardButton(text=text, **kwargs)
    try:
        button = InlineKeyboardButton(text=text, style=style, **kwargs)
        _STYLE_SUPPORTED = True
        return button
    except Exception:  # pragma: no cover - depends on aiogram/Telegram version
        _STYLE_SUPPORTED = False
        return InlineKeyboardButton(text=text, **kwargs)


def green(text: str, **kwargs: Any) -> InlineKeyboardButton:
    """Positive action / in-stock item."""
    return btn(text, SUCCESS, **kwargs)


def red(text: str, **kwargs: Any) -> InlineKeyboardButton:
    """Destructive action / out-of-stock item."""
    return btn(text, DANGER, **kwargs)


def sky(text: str, **kwargs: Any) -> InlineKeyboardButton:
    """Navigation: Back / Cancel / Main Menu."""
    return btn(text, PRIMARY, **kwargs)


def stock_btn(text: str, in_stock: bool, **kwargs: Any) -> InlineKeyboardButton:
    """Green when the product has stock, red when it is sold out."""
    return btn(text, SUCCESS if in_stock else DANGER, **kwargs)


# ── Premium (custom) emoji ───────────────────────────────────────────────────

# name -> (fallback unicode emoji, default custom emoji id)
PREMIUM_EMOJI: Dict[str, str] = {
    "fire":     "🔥",
    "star":     "⭐",
    "crown":    "👑",
    "diamond":  "💎",
    "cart":     "🛒",
    "shop":     "🛍️",
    "wallet":   "👛",
    "money":    "💰",
    "card":     "💳",
    "gift":     "🎁",
    "rocket":   "🚀",
    "bell":     "🔔",
    "check":    "✅",
    "cross":    "❌",
    "lock":     "🔐",
    "support":  "🎧",
    "user":     "👤",
    "link":     "🔗",
    "box":      "📦",
    "bolt":     "⚡",
    "sparkles": "✨",
    "warning":  "⚠️",
    "back":     "◀️",
    "home":     "🏠",
    "megaphone": "📣",
    "trophy":   "🏆",
    "shield":   "🛡",
    "truck":    "🚚",
    "clock":    "⏳",
    "chart":    "📊",
}

# Runtime cache of {emoji_name: custom_emoji_id}; filled from the DB setting
# "premium_emoji_ids" (JSON) by refresh_premium_emoji().
_CUSTOM_IDS: Dict[str, str] = {}


def set_custom_emoji_ids(mapping: Dict[str, str]) -> None:
    _CUSTOM_IDS.clear()
    _CUSTOM_IDS.update({k: str(v) for k, v in (mapping or {}).items() if v})


def get_custom_emoji_ids() -> Dict[str, str]:
    return dict(_CUSTOM_IDS)


def pe(name: str, fallback: Optional[str] = None) -> str:
    """Return premium emoji HTML for *name*, or the plain emoji fallback."""
    emoji = fallback or PREMIUM_EMOJI.get(name, "")
    if not emoji:
        return ""
    custom_id = _CUSTOM_IDS.get(name)
    if custom_id:
        return f'<tg-emoji emoji-id="{custom_id}">{emoji}</tg-emoji>'
    return emoji


async def refresh_premium_emoji() -> None:
    """Load custom emoji IDs from the settings table into the cache."""
    import json

    from bot.database import get_setting

    raw = await get_setting("premium_emoji_ids")
    try:
        set_custom_emoji_ids(json.loads(raw) if raw else {})
    except Exception:
        set_custom_emoji_ids({})


# ── Text helpers ─────────────────────────────────────────────────────────────

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def title(text: str, emoji_name: str = "sparkles") -> str:
    return f"{pe(emoji_name)} <b>{text}</b>\n{DIVIDER}"


def money(value: float) -> str:
    return f"${value:,.2f}"
