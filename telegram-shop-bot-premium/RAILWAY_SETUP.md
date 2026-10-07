# Railway setup

1. Upload this project to GitHub and deploy the repository on Railway.
2. In the Railway service, open **Variables** and add:
   - `BOT_TOKEN`: the token from BotFather (required)
   - `ADMIN_IDS`: comma-separated numeric Telegram user IDs (recommended)
3. Redeploy the service. The Dockerfile installs Python dependencies and starts
   the bot with `python -m bot.main`.

## Database persistence

The bot defaults to storing SQLite data at `bot/shop.db`. Railway's normal
service filesystem is ephemeral, so data may be lost after redeploys. For
production use, attach a Railway Volume mounted at `/data`, then add the Railway
variable `DB_PATH=/data/shop.db`. Alternatively, migrate the bot to Postgres.

## Binance Auto Payment (new)

Add these two variables in Railway → Variables:

- `BINANCE_API_KEY` — Binance API key with **Enable Reading only**
- `BINANCE_API_SECRET` — the matching secret

Then in the bot: `/admin` → **🟡 Binance Auto Pay** to turn auto-detection on,
set the time window, test the API connection and view verified payments.

Users pay to your Binance Pay ID / USDT address, submit the **Order ID**, and
the bot verifies **order id + amount + time** automatically and credits the
balance. Nothing can be withdrawn with a read-only key.

## Other new admin features

- 🔒 **Force Join** — require channel membership before using the bot
- 🧩 **Menu Buttons** — add/remove your own buttons under the main menu
- ✨ **Premium Emoji** — map premium custom-emoji IDs used across the bot
- 📢 **Broadcast** — now sends a premium *BACK IN STOCK* card with a green **BUY NOW** button
