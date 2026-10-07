import os
from typing import List

BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")

# Admin IDs — set via the ADMIN_IDS environment variable (comma-separated Telegram user IDs).
# Example: ADMIN_IDS="8559195254,9876543210"
# When ADMIN_IDS is not set, a single default admin ID is used.
# To remove the default admin, set ADMIN_IDS to only the IDs you want — no ID is silently re-added.
_ADMIN_IDS_STR: str = os.environ.get("ADMIN_IDS", "8559195254")
ADMIN_IDS: List[int] = [
    int(x.strip()) for x in _ADMIN_IDS_STR.split(",") if x.strip().isdigit()
]

if not ADMIN_IDS:
    raise RuntimeError(
        f"ADMIN_IDS is set to {_ADMIN_IDS_STR!r} but contains no valid integer Telegram user IDs. "
        "Set ADMIN_IDS to a comma-separated list of numeric Telegram IDs (e.g. ADMIN_IDS=8559195254) "
        "and restart the bot."
    )

DB_PATH: str = os.environ.get("DB_PATH", "bot/shop.db")

# ─── Binance (read-only API key — used only to VERIFY incoming payments) ─────
# Set these as Railway variables. The key must have "Enable Reading" only.
BINANCE_API_KEY: str = os.environ.get("BINANCE_API_KEY", "")
BINANCE_API_SECRET: str = os.environ.get("BINANCE_API_SECRET", "")

# Sales announcement group — bot must be admin in this group
SALES_GROUP_ID: int = -1003836326815
BOT_USERNAME: str = "Paktools_bot"

# Economy
REFERRAL_BONUS: float = 0.05   # default; overridden by DB setting "referral_bonus"
DAILY_FREEBIE_AMOUNT: float = 0.05
FREEBIE_CHANNEL: str = "@paktoolsofficial"   # must join before claiming
# No welcome bonus — new users start at $0

# ─── Membership Tiers (auto-upgrade based on total purchases) ───────────────
# Tiers upgrade automatically when the user's total completed spending reaches
# the threshold. There is no subscription fee — it's earned by spending.
MEMBERSHIP_TIERS = {
    "none":    {"name": "🔓 Free",    "min_spent": 0,   "discount": 0.00},
    "bronze":  {"name": "🥉 Bronze",  "min_spent": 10,  "discount": 0.03},
    "silver":  {"name": "🥈 Silver",  "min_spent": 50,  "discount": 0.07},
    "gold":    {"name": "🥇 Gold",    "min_spent": 150, "discount": 0.12},
    "diamond": {"name": "💎 Diamond", "min_spent": 300, "discount": 0.18},
}

CURRENCY_SYMBOL = "💰"
BOT_NAME = "PremiumShop"

# Default payment details (can be updated by admin from Telegram via /admin)
DEFAULT_SETTINGS = {
    "sadapay_number":  "0300-0000000",
    "binance_trc20":   "TYourTRC20AddressHere",
    "binance_bep20":   "0xYourBEP20AddressHere",
    "binance_pay_id":  "YourBinancePayID",
    "referral_bonus":  "0.05",
    "low_stock_threshold": "3",
    # ── Binance auto payment ────────────────────────────────────────────────
    "binance_auto_enabled": "1",       # 1 = auto-detect payments, 0 = manual only
    "binance_window_hours": "24",      # how far back to search for the payment
    "binance_amount_only": "0",        # 1 = also accept amount+time match w/o order id
    # ── Force channel join ──────────────────────────────────────────────────
    "force_join_enabled": "0",
    "force_join_channels": "@paktoolsofficial",
    # ── Custom main-menu buttons (JSON list, managed from the admin panel) ──
    "custom_menu_buttons": "[]",
    # ── Premium (custom) emoji IDs (JSON: {"fire": "5368324170671202286"}) ──
    "premium_emoji_ids": "{}",
    # ── Branding ────────────────────────────────────────────────────────────
    "broadcast_title": "BACK IN STOCK",
}

# Default products (name, description, price)
DEFAULT_PRODUCTS = [
    ("CapCut Pro",      "CapCut Pro subscription — unlock all premium editing tools, templates & effects. Instant delivery.", 4.99),
    ("Canva Pro",       "Canva Pro account — full access to premium templates, assets, Brand Kit & more. Instant delivery.", 4.99),
    ("Google AI Pro",   "Google AI Pro plan — Gemini Advanced with 2TB storage and AI features across Google apps.", 9.99),
    ("Veo 3 Ultra",     "Veo 3 Ultra access — Google's most advanced AI video generation model. Create stunning videos.", 14.99),
    ("Extension Based", "Premium browser extension subscription — unlock advanced productivity & automation tools.", 3.99),
    ("ChatGPT Plus",    "ChatGPT Plus subscription — GPT-4o, image generation, advanced reasoning & more.", 9.99),
    ("Hotmails",        "Fresh Hotmail / Outlook accounts — verified and ready to use. Bulk available.", 1.99),
    ("Gmails",          "Fresh Gmail accounts — phone verified, aged accounts available. Bulk available.", 1.99),
    ("Lovable Lite",    "Lovable Lite plan — AI-powered app builder with expanded monthly credits.", 5.99),
    ("Super Grok",      "Super Grok subscription — xAI's most powerful model with unlimited usage.", 12.99),
]
