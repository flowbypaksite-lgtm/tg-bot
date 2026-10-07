import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from bot.config import DB_PATH, DEFAULT_PRODUCTS, MEMBERSHIP_TIERS, DEFAULT_SETTINGS


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                balance REAL DEFAULT 0.0,
                referred_by INTEGER,
                membership_type TEXT DEFAULT 'none',
                is_banned INTEGER DEFAULT 0,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_activity TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL DEFAULT 0.0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS stock_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                account_data TEXT NOT NULL,
                is_used INTEGER DEFAULT 0,
                used_by_user_id INTEGER,
                used_in_order_id INTEGER,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                used_at TEXT,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                stock_item_id INTEGER,
                quantity INTEGER DEFAULT 1,
                total_price REAL NOT NULL,
                status TEXT DEFAULT 'completed',
                account_delivered TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS freebies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                last_claimed TEXT,
                streak INTEGER DEFAULT 0,
                total_claimed REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                bonus_paid INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pending_deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                method TEXT NOT NULL,
                screenshot_file_id TEXT,
                admin_message_ids TEXT DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                checkout_product_id INTEGER DEFAULT NULL,
                checkout_qty INTEGER DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                processed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS redeem_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                amount REAL NOT NULL,
                usage_limit INTEGER DEFAULT 1,
                times_used INTEGER DEFAULT 0,
                expires_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS redeem_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                used_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS binance_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                telegram_id INTEGER,
                amount REAL NOT NULL,
                currency TEXT,
                source TEXT,
                purpose TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS product_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(telegram_id, product_id)
            );
        """)

        # Seed default products if empty
        cursor = await db.execute("SELECT COUNT(*) FROM products")
        if (await cursor.fetchone())[0] == 0:
            for name, desc, price in DEFAULT_PRODUCTS:
                await db.execute(
                    "INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
                    (name, desc, price),
                )

        # Seed default settings if missing
        for key, val in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, val),
            )

        # ── Schema migrations (safe: ignore if column already exists) ───────────
        for _migration_sql in [
            "ALTER TABLE products ADD COLUMN logo TEXT",
            "ALTER TABLE products ADD COLUMN logo_file_id TEXT",
            "ALTER TABLE products ADD COLUMN status_emoji TEXT",
            "ALTER TABLE products ADD COLUMN warranty TEXT",
            "ALTER TABLE products ADD COLUMN product_type TEXT",
            "ALTER TABLE products ADD COLUMN delivery_type TEXT",
            "ALTER TABLE pending_deposits ADD COLUMN checkout_product_id INTEGER DEFAULT NULL",
            "ALTER TABLE pending_deposits ADD COLUMN checkout_qty INTEGER DEFAULT NULL",
            "ALTER TABLE products ADD COLUMN custom_buttons TEXT DEFAULT NULL",
        ]:
            try:
                await db.execute(_migration_sql)
                await db.commit()
            except Exception:
                pass  # column already exists

        await db.commit()


# ─── SETTINGS ────────────────────────────────────────────────────────────────

async def get_setting(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else DEFAULT_SETTINGS.get(key)


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value),
        )
        await db.commit()


# ─── ADMIN IDs (DB-backed, live source) ──────────────────────────────────────

async def get_admin_ids() -> List[int]:
    """Return the current admin ID list from the DB setting 'active_admin_ids'.

    Falls back to the env-var-derived ADMIN_IDS if the setting is absent so
    the first startup doesn't require a separate initialisation step.
    """
    from bot.config import ADMIN_IDS as _env_admin_ids  # local import to avoid circular
    raw = await get_setting("active_admin_ids")
    if not raw:
        return list(_env_admin_ids)
    ids = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
    return ids if ids else list(_env_admin_ids)


async def set_admin_ids(admin_ids: List[int]) -> None:
    """Persist a new admin ID list to the DB setting 'active_admin_ids'."""
    await set_setting("active_admin_ids", ",".join(str(i) for i in admin_ids))


async def seed_admin_ids(admin_ids: List[int]) -> None:
    """Seed 'active_admin_ids' from the env-var list only if the setting is not
    already present in the DB.  Used at startup so that DB-managed admin IDs
    (set via bot commands or external writes) are not overwritten on every boot.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            ("active_admin_ids", ",".join(str(i) for i in admin_ids)),
        )
        await db.commit()


# ─── USERS ───────────────────────────────────────────────────────────────────

async def get_or_create_user(
    telegram_id: int,
    username: str = None,
    first_name: str = None,
    last_name: str = None,
    referral_code: str = None,   # now the referrer's telegram_id as a string
) -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        user = await cursor.fetchone()
        if user:
            await db.execute(
                "UPDATE users SET username=?, first_name=?, last_name=?, last_activity=CURRENT_TIMESTAMP WHERE telegram_id=?",
                (username, first_name, last_name, telegram_id),
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
            return dict(await cursor.fetchone())

        # New user — resolve referrer by their telegram_id (the referral code IS the telegram_id)
        referred_by_id = None
        if referral_code and referral_code.isdigit():
            ref_tg_id = int(referral_code)
            if ref_tg_id != telegram_id:  # prevent self-referral
                rc = await db.execute("SELECT id FROM users WHERE telegram_id=?", (ref_tg_id,))
                ref_row = await rc.fetchone()
                if ref_row:
                    referred_by_id = ref_row["id"]

        # Insert new user — no welcome bonus, starts at $0
        await db.execute(
            "INSERT INTO users (telegram_id, username, first_name, last_name, balance, referred_by) VALUES (?, ?, ?, ?, 0.0, ?)",
            (telegram_id, username, first_name, last_name, referred_by_id),
        )
        cur2 = await db.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
        new_id = (await cur2.fetchone())[0]

        # Register referral relationship (bonus paid when first purchase is made)
        if referred_by_id:
            await db.execute(
                "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                (referred_by_id, new_id),
            )

        await db.commit()
        cursor = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        return dict(await cursor.fetchone())


async def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE id=?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def search_users(query: str) -> List[Dict[str, Any]]:
    """Search users by username, first name, or telegram ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        like = f"%{query}%"
        cursor = await db.execute(
            """SELECT * FROM users
               WHERE username LIKE ? OR first_name LIKE ? OR CAST(telegram_id AS TEXT) LIKE ?
               ORDER BY joined_at DESC LIMIT 20""",
            (like, like, like),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def update_balance(user_id: int, amount: float, tx_type: str, description: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, user_id))
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
            (user_id, tx_type, amount, description),
        )
        await db.commit()


async def set_user_balance(user_id: int, new_balance: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=? WHERE id=?", (new_balance, user_id))
        await db.commit()


async def ban_user(user_id: int, banned: bool = True):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=? WHERE id=?", (1 if banned else 0, user_id))
        await db.commit()


async def get_all_users() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users ORDER BY joined_at DESC")
        return [dict(r) for r in await cursor.fetchall()]


async def get_stats() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        users    = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        orders   = (await (await db.execute("SELECT COUNT(*) FROM orders")).fetchone())[0]
        revenue  = (await (await db.execute(
            "SELECT COALESCE(SUM(total_price),0) FROM orders WHERE status='completed'"
        )).fetchone())[0]
        products = (await (await db.execute("SELECT COUNT(*) FROM products WHERE is_active=1")).fetchone())[0]
        today    = datetime.now().strftime("%Y-%m-%d")
        new_today = (await (await db.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",)
        )).fetchone())[0]
        total_stock = (await (await db.execute(
            "SELECT COUNT(*) FROM stock_items WHERE is_used=0"
        )).fetchone())[0]
        pending_deps = (await (await db.execute(
            "SELECT COUNT(*) FROM pending_deposits WHERE status='pending'"
        )).fetchone())[0]
        return {
            "users": users, "orders": orders, "revenue": revenue,
            "products": products, "new_today": new_today,
            "total_stock": total_stock, "pending_deposits": pending_deps,
        }


# ─── MEMBERSHIP (auto-tier based on total spend) ──────────────────────────────

def _tier_for_spent(total_spent: float) -> str:
    tier = "none"
    for key, info in MEMBERSHIP_TIERS.items():
        if total_spent >= info["min_spent"]:
            tier = key
    return tier


async def auto_upgrade_membership(user_id: int) -> Optional[str]:
    """Recalculate tier from total spend. Returns new tier name if upgraded, else None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT COALESCE(SUM(total_price),0) FROM orders WHERE user_id=? AND status='completed'",
            (user_id,),
        )
        total_spent = (await cur.fetchone())[0]
        new_tier = _tier_for_spent(total_spent)

        cur2 = await db.execute("SELECT membership_type FROM users WHERE id=?", (user_id,))
        row = await cur2.fetchone()
        current_tier = row["membership_type"] if row else "none"

        if new_tier != current_tier:
            await db.execute("UPDATE users SET membership_type=? WHERE id=?", (new_tier, user_id))
            await db.commit()
            return new_tier
        return None


async def get_membership_discount(user: Dict) -> float:
    tier = user.get("membership_type", "none")
    return MEMBERSHIP_TIERS.get(tier, {}).get("discount", 0.0)


async def is_membership_active(user: Dict) -> bool:
    return user.get("membership_type", "none") != "none"


# ─── PRODUCTS ────────────────────────────────────────────────────────────────

async def get_products(active_only: bool = True) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM products WHERE is_active=1 ORDER BY id" if active_only else "SELECT * FROM products ORDER BY id"
        products = [dict(r) for r in await (await db.execute(q)).fetchall()]
        for p in products:
            cnt = await db.execute("SELECT COUNT(*) FROM stock_items WHERE product_id=? AND is_used=0", (p["id"],))
            p["stock_count"] = (await cnt.fetchone())[0]
        return products


async def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products WHERE id=?", (product_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        p = dict(row)
        cnt = await db.execute("SELECT COUNT(*) FROM stock_items WHERE product_id=? AND is_used=0", (product_id,))
        p["stock_count"] = (await cnt.fetchone())[0]
        return p


async def add_product(name: str, description: str, price: float) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
            (name, description, price),
        )
        await db.commit()
        return cursor.lastrowid


# ─── Product Alerts ──────────────────────────────────────────────────────────

async def toggle_product_alert(telegram_id: int, product_id: int) -> bool:
    """Toggle alert subscription. Returns True if alert was added, False if removed."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM product_alerts WHERE telegram_id=? AND product_id=?",
            (telegram_id, product_id),
        )
        row = await cursor.fetchone()
        if row:
            await db.execute(
                "DELETE FROM product_alerts WHERE telegram_id=? AND product_id=?",
                (telegram_id, product_id),
            )
            await db.commit()
            return False
        else:
            await db.execute(
                "INSERT OR IGNORE INTO product_alerts (telegram_id, product_id) VALUES (?,?)",
                (telegram_id, product_id),
            )
            await db.commit()
            return True


async def has_product_alert(telegram_id: int, product_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM product_alerts WHERE telegram_id=? AND product_id=?",
            (telegram_id, product_id),
        )
        return (await cursor.fetchone()) is not None


async def get_product_alert_subscribers(product_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT telegram_id FROM product_alerts WHERE product_id=?",
            (product_id,),
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def update_product(
    product_id: int,
    name: str = None,
    description: str = None,
    price: float = None,
    logo: str = None,
    logo_file_id: str = None,
    status_emoji: str = None,
    warranty: str = None,
    product_type: str = None,
    delivery_type: str = None,
    custom_buttons: str = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        if name is not None:
            await db.execute("UPDATE products SET name=? WHERE id=?", (name, product_id))
        if description is not None:
            await db.execute("UPDATE products SET description=? WHERE id=?", (description, product_id))
        if price is not None:
            await db.execute("UPDATE products SET price=? WHERE id=?", (price, product_id))
        if logo is not None:
            await db.execute("UPDATE products SET logo=? WHERE id=?", (logo, product_id))
        if logo_file_id is not None:
            val = None if logo_file_id == "" else logo_file_id
            await db.execute("UPDATE products SET logo_file_id=? WHERE id=?", (val, product_id))
        if status_emoji is not None:
            val = None if status_emoji == "" else status_emoji
            await db.execute("UPDATE products SET status_emoji=? WHERE id=?", (val, product_id))
        if warranty is not None:
            await db.execute("UPDATE products SET warranty=? WHERE id=?", (warranty, product_id))
        if product_type is not None:
            await db.execute("UPDATE products SET product_type=? WHERE id=?", (product_type, product_id))
        if delivery_type is not None:
            await db.execute("UPDATE products SET delivery_type=? WHERE id=?", (delivery_type, product_id))
        if custom_buttons is not None:
            await db.execute("UPDATE products SET custom_buttons=? WHERE id=?", (custom_buttons, product_id))
        await db.commit()


async def delete_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM stock_items WHERE product_id=?", (product_id,))
        await db.execute("DELETE FROM products WHERE id=?", (product_id,))
        await db.commit()


async def toggle_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE products SET is_active=1-is_active WHERE id=?", (product_id,))
        await db.commit()


# ─── STOCK ───────────────────────────────────────────────────────────────────

async def add_stock_items(product_id: int, accounts: List[str]) -> Dict[str, Any]:
    """Validate, deduplicate, and insert stock lines.

    Returns a dict with keys:
      added             — number of lines successfully inserted
      skipped_duplicate — lines already in stock (or repeated within the batch)
      skipped_invalid   — lines that don't match 'value' or 'left:right' format
      invalid_lines     — list of the rejected malformed lines (up to 20)
      duplicate_lines   — list of the rejected duplicate lines (up to 20)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Load existing unused stock for this product to detect duplicates
        cursor = await db.execute(
            "SELECT account_data FROM stock_items WHERE product_id=? AND is_used=0",
            (product_id,),
        )
        existing: set = {row[0] for row in await cursor.fetchall()}

        added = 0
        skipped_duplicate = 0
        skipped_invalid = 0
        invalid_lines: List[str] = []
        duplicate_lines: List[str] = []
        seen_in_batch: set = set()

        for raw in accounts:
            acc = raw.strip()
            if not acc:
                continue

            # Validate: if a colon is present both sides must be non-empty
            if ":" in acc:
                left, right = acc.split(":", 1)
                if not left.strip() or not right.strip():
                    skipped_invalid += 1
                    if len(invalid_lines) < 20:
                        invalid_lines.append(acc)
                    continue
            # Plain value (no colon) is always valid as long as it's non-empty

            # Duplicate check: already in DB or already seen in this batch
            if acc in existing or acc in seen_in_batch:
                skipped_duplicate += 1
                if len(duplicate_lines) < 20:
                    duplicate_lines.append(acc)
                continue

            await db.execute(
                "INSERT INTO stock_items (product_id, account_data) VALUES (?, ?)",
                (product_id, acc),
            )
            seen_in_batch.add(acc)
            added += 1

        await db.commit()

    return {
        "added": added,
        "skipped_duplicate": skipped_duplicate,
        "skipped_invalid": skipped_invalid,
        "invalid_lines": invalid_lines,
        "duplicate_lines": duplicate_lines,
    }


async def remove_stock_items(product_id: int, count: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM stock_items WHERE product_id=? AND is_used=0 LIMIT ?", (product_id, count)
        )
        ids = [r[0] for r in await cursor.fetchall()]
        if ids:
            await db.execute(f"DELETE FROM stock_items WHERE id IN ({','.join('?'*len(ids))})", ids)
            await db.commit()
        return len(ids)


async def get_stock_items(product_id: int, used: bool = False) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM stock_items WHERE product_id=? AND is_used=? ORDER BY added_at",
            (product_id, 1 if used else 0),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def claim_stock_item(product_id: int, user_id: int, order_id: int) -> Optional[str]:
    """Atomically claim the first available stock item. Returns account_data or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, account_data FROM stock_items WHERE product_id=? AND is_used=0 ORDER BY id LIMIT 1",
            (product_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        item_id, account_data = row[0], row[1]
        now = datetime.now().isoformat()
        await db.execute(
            "UPDATE stock_items SET is_used=1, used_by_user_id=?, used_in_order_id=?, used_at=? WHERE id=?",
            (user_id, order_id, now, item_id),
        )
        await db.execute(
            "UPDATE orders SET stock_item_id=?, account_delivered=? WHERE id=?",
            (item_id, account_data, order_id),
        )
        await db.commit()
        return account_data


# ─── ORDERS ──────────────────────────────────────────────────────────────────

async def has_claimed_free_product(user_id: int, product_id: int) -> bool:
    """Returns True if this user already has a completed order for this product."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM orders WHERE user_id=? AND product_id=? AND status='completed' LIMIT 1",
            (user_id, product_id),
        )
        return await cursor.fetchone() is not None


async def create_order(user_id: int, product_id: int, price: float) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, product_id, total_price, status) VALUES (?, ?, ?, 'pending')",
            (user_id, product_id, price),
        )
        order_id = cursor.lastrowid
        await db.execute("UPDATE users SET balance=balance-? WHERE id=?", (price, user_id))
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
            (user_id, "purchase", -price, f"Order #{order_id}"),
        )
        await db.commit()
        return order_id


async def complete_order(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status='completed' WHERE id=?", (order_id,))
        await db.commit()


async def refund_order(order_id: int, user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status='refunded' WHERE id=?", (order_id,))
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, user_id))
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
            (user_id, "refund", amount, f"Refund for order #{order_id}"),
        )
        await db.commit()


async def get_user_orders(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT o.*, p.name as product_name
               FROM orders o LEFT JOIN products p ON o.product_id=p.id
               WHERE o.user_id=? ORDER BY o.created_at DESC LIMIT 20""",
            (user_id,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_user_total_spent(user_id: int) -> float:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COALESCE(SUM(total_price),0) FROM orders WHERE user_id=? AND status='completed'",
            (user_id,),
        )
        return (await cur.fetchone())[0]


async def get_all_orders(limit: int = 50) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT o.*, p.name as product_name, u.first_name, u.username, u.telegram_id
               FROM orders o
               LEFT JOIN products p ON o.product_id=p.id
               LEFT JOIN users u ON o.user_id=u.id
               ORDER BY o.created_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in await cursor.fetchall()]


# ─── TRANSACTIONS ─────────────────────────────────────────────────────────────

async def get_transactions(user_id: int, limit: int = 15) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


# ─── FREEBIES ────────────────────────────────────────────────────────────────

async def claim_freebie(user_id: int, amount: float) -> Dict[str, Any]:
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM freebies WHERE user_id=?", (user_id,))
        record = await cursor.fetchone()
        if record:
            record = dict(record)
            last = record.get("last_claimed", "")
            if last and last.startswith(today):
                next_claim = datetime.strptime(last[:10], "%Y-%m-%d") + timedelta(days=1)
                return {"success": False, "seconds_left": int((next_claim - now).total_seconds()), "streak": record["streak"]}
            yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            streak = record["streak"] + 1 if (last and last.startswith(yesterday)) else 1
            bonus = amount * (1 + (streak - 1) * 0.1)
            await db.execute(
                "UPDATE freebies SET last_claimed=?, streak=?, total_claimed=total_claimed+? WHERE user_id=?",
                (now.isoformat(), streak, bonus, user_id),
            )
        else:
            bonus = amount
            streak = 1
            await db.execute(
                "INSERT INTO freebies (user_id, last_claimed, streak, total_claimed) VALUES (?, ?, 1, ?)",
                (user_id, now.isoformat(), bonus),
            )
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (bonus, user_id))
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
            (user_id, "freebie", bonus, f"Daily freebie (streak #{streak})"),
        )
        await db.commit()
        return {"success": True, "amount": bonus, "streak": streak}


async def get_freebie_status(user_id: int) -> Dict[str, Any]:
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM freebies WHERE user_id=?", (user_id,))
        record = await cursor.fetchone()
        if not record:
            return {"can_claim": True, "streak": 0, "total_claimed": 0.0, "seconds_left": 0}
        record = dict(record)
        last = record.get("last_claimed", "")
        if last and last.startswith(today):
            next_claim = datetime.strptime(last[:10], "%Y-%m-%d") + timedelta(days=1)
            return {
                "can_claim": False, "streak": record["streak"],
                "total_claimed": record["total_claimed"],
                "seconds_left": max(0, int((next_claim - now).total_seconds())),
            }
        return {"can_claim": True, "streak": record["streak"], "total_claimed": record["total_claimed"], "seconds_left": 0}


# ─── REFERRALS ───────────────────────────────────────────────────────────────

async def get_referrals(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT r.*, u.first_name, u.username, u.joined_at
               FROM referrals r JOIN users u ON r.referred_id=u.id
               WHERE r.referrer_id=? ORDER BY r.created_at DESC""",
            (user_id,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_referral_earnings(user_id: int) -> float:
    """Total referral bonuses earned."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND type='referral_bonus'",
            (user_id,),
        )
        return (await cur.fetchone())[0]


async def pay_referral_bonus(referrer_id: int, referred_id: int, amount: float):
    """Pay the referral bonus once (first purchase by referred user)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Mark as paid
        await db.execute(
            "UPDATE referrals SET bonus_paid=1 WHERE referrer_id=? AND referred_id=?",
            (referrer_id, referred_id),
        )
        # Credit the referrer
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, referrer_id))
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
            (referrer_id, "referral_bonus", amount, "Referral bonus"),
        )
        await db.commit()


# ─── PENDING DEPOSITS ────────────────────────────────────────────────────────

async def create_pending_deposit(
    user_id: int,
    telegram_id: int,
    amount: float,
    method: str,
    screenshot_file_id: str,
    checkout_product_id: int = None,
    checkout_qty: int = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO pending_deposits
               (user_id, telegram_id, amount, method, screenshot_file_id, checkout_product_id, checkout_qty)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, telegram_id, amount, method, screenshot_file_id, checkout_product_id, checkout_qty),
        )
        await db.commit()
        return cursor.lastrowid


async def get_pending_deposit(deposit_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM pending_deposits WHERE id=?", (deposit_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_pending_deposits() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT pd.*, u.first_name, u.username
               FROM pending_deposits pd LEFT JOIN users u ON pd.user_id=u.id
               WHERE pd.status='pending' ORDER BY pd.created_at DESC"""
        )
        return [dict(r) for r in await cursor.fetchall()]


async def approve_deposit(deposit_id: int) -> Optional[Dict[str, Any]]:
    """Approve a pending deposit: add balance to user, return deposit info."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM pending_deposits WHERE id=? AND status='pending'", (deposit_id,))
        dep = await cursor.fetchone()
        if not dep:
            return None
        dep = dict(dep)
        # Add balance
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (dep["amount"], dep["user_id"]))
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
            (dep["user_id"], "deposit", dep["amount"], f"Deposit via {dep['method']} approved"),
        )
        await db.execute(
            "UPDATE pending_deposits SET status='approved', processed_at=CURRENT_TIMESTAMP WHERE id=?",
            (deposit_id,),
        )
        await db.commit()
        return dep


async def reject_deposit(deposit_id: int) -> Optional[Dict[str, Any]]:
    """Reject a pending deposit. Returns deposit info."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM pending_deposits WHERE id=? AND status='pending'", (deposit_id,))
        dep = await cursor.fetchone()
        if not dep:
            return None
        dep = dict(dep)
        await db.execute(
            "UPDATE pending_deposits SET status='rejected', processed_at=CURRENT_TIMESTAMP WHERE id=?",
            (deposit_id,),
        )
        await db.commit()
        return dep


# ─── REDEEM CODES ────────────────────────────────────────────────────────────

async def create_redeem_code(
    code: str, amount: float, usage_limit: int = 1, expires_at: Optional[str] = None
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO redeem_codes (code, amount, usage_limit, expires_at) VALUES (?, ?, ?, ?)",
            (code.upper().strip(), amount, usage_limit, expires_at),
        )
        await db.commit()
        return cursor.lastrowid


async def get_redeem_code(code: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM redeem_codes WHERE code=?", (code.upper().strip(),)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def use_redeem_code(code: str, user_id: int) -> Dict[str, Any]:
    """Try to redeem a code for a user. Returns {success, amount, reason}."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM redeem_codes WHERE code=?", (code.upper().strip(),)
        )
        rc = await cursor.fetchone()
        if not rc:
            return {"success": False, "reason": "invalid"}
        rc = dict(rc)

        # Check expiry
        if rc["expires_at"]:
            try:
                exp = datetime.fromisoformat(rc["expires_at"])
                if datetime.now() > exp:
                    return {"success": False, "reason": "expired"}
            except Exception:
                pass

        # Check usage limit
        if rc["times_used"] >= rc["usage_limit"]:
            return {"success": False, "reason": "exhausted"}

        # Check if this user already used it
        dup = await db.execute(
            "SELECT id FROM redeem_uses WHERE code_id=? AND user_id=?",
            (rc["id"], user_id),
        )
        if await dup.fetchone():
            return {"success": False, "reason": "already_used"}

        # Redeem
        await db.execute(
            "INSERT INTO redeem_uses (code_id, user_id) VALUES (?, ?)",
            (rc["id"], user_id),
        )
        await db.execute(
            "UPDATE redeem_codes SET times_used=times_used+1 WHERE id=?", (rc["id"],)
        )
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (rc["amount"], user_id))
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
            (user_id, "redeem", rc["amount"], f"Redeem code: {rc['code']}"),
        )
        await db.commit()
        return {"success": True, "amount": rc["amount"], "code": rc["code"]}


async def get_all_redeem_codes() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM redeem_codes ORDER BY created_at DESC"
        )
        return [dict(r) for r in await cursor.fetchall()]


async def delete_redeem_code(code_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM redeem_uses WHERE code_id=?", (code_id,))
        await db.execute("DELETE FROM redeem_codes WHERE id=?", (code_id,))
        await db.commit()


# ─── SUPPORT TICKETS ─────────────────────────────────────────────────────────

async def create_support_ticket(user_id: int, telegram_id: int, message: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO support_tickets (user_id, telegram_id, message) VALUES (?, ?, ?)",
            (user_id, telegram_id, message),
        )
        await db.commit()
        return cursor.lastrowid


# ─── BINANCE AUTO PAYMENTS ───────────────────────────────────────────────────

async def get_used_binance_ids() -> List[str]:
    """All Binance order/tx ids already credited (prevents re-use)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT order_id FROM binance_payments")
        return [r[0] for r in await cursor.fetchall()]


async def is_binance_id_used(order_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM binance_payments WHERE LOWER(order_id)=LOWER(?)", (order_id,)
        )
        return await cursor.fetchone() is not None


async def record_binance_payment(
    order_id: str,
    user_id: int,
    telegram_id: int,
    amount: float,
    currency: str = "USDT",
    source: str = "",
    purpose: str = "deposit",
) -> bool:
    """Store a verified payment. Returns False if the id was already used."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO binance_payments
                   (order_id, user_id, telegram_id, amount, currency, source, purpose)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (order_id, user_id, telegram_id, amount, currency, source, purpose),
            )
            await db.commit()
            return True
        except Exception:
            return False


async def get_binance_payments(limit: int = 20) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT bp.*, u.first_name, u.username
               FROM binance_payments bp LEFT JOIN users u ON bp.user_id = u.id
               ORDER BY bp.created_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in await cursor.fetchall()]


# ─── CUSTOM MAIN-MENU BUTTONS ────────────────────────────────────────────────

async def get_custom_menu_buttons() -> List[Dict[str, Any]]:
    """Extra main-menu buttons added by admins.

    Each item: {"label": str, "type": "url"|"text", "value": str,
                "style": "primary"|"success"|"danger"}
    """
    import json
    raw = await get_setting("custom_menu_buttons")
    try:
        data = json.loads(raw or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []


async def save_custom_menu_buttons(buttons: List[Dict[str, Any]]) -> None:
    import json
    await set_setting("custom_menu_buttons", json.dumps(buttons))


async def add_custom_menu_button(label: str, btype: str, value: str, style: str = "primary") -> None:
    buttons = await get_custom_menu_buttons()
    buttons.append({"label": label, "type": btype, "value": value, "style": style})
    await save_custom_menu_buttons(buttons)


async def delete_custom_menu_button(index: int) -> bool:
    buttons = await get_custom_menu_buttons()
    if 0 <= index < len(buttons):
        buttons.pop(index)
        await save_custom_menu_buttons(buttons)
        return True
    return False


# ─── FORCE CHANNEL JOIN ──────────────────────────────────────────────────────

async def get_force_join_config() -> Dict[str, Any]:
    enabled = (await get_setting("force_join_enabled")) == "1"
    raw = await get_setting("force_join_channels") or ""
    channels = [c.strip() for c in raw.split(",") if c.strip()]
    return {"enabled": enabled, "channels": channels}


async def set_force_join_enabled(enabled: bool) -> None:
    await set_setting("force_join_enabled", "1" if enabled else "0")


async def set_force_join_channels(channels: List[str]) -> None:
    await set_setting("force_join_channels", ",".join(channels))


# ─── PREMIUM EMOJI IDS ───────────────────────────────────────────────────────

async def get_premium_emoji_ids() -> Dict[str, str]:
    import json
    raw = await get_setting("premium_emoji_ids")
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def set_premium_emoji_id(name: str, emoji_id: str) -> Dict[str, str]:
    import json
    mapping = await get_premium_emoji_ids()
    if emoji_id:
        mapping[name] = emoji_id
    else:
        mapping.pop(name, None)
    await set_setting("premium_emoji_ids", json.dumps(mapping))
    return mapping
