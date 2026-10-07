import asyncio
import logging
import sys
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat

import bot.config as _config
from bot.config import BOT_TOKEN, ADMIN_IDS
from bot.database import init_db, get_setting, set_setting, get_admin_ids, set_admin_ids, seed_admin_ids
from typing import List
from bot.middlewares.user import UserMiddleware
from bot.middlewares.force_join import ForceJoinMiddleware
from bot.utils.ui import refresh_premium_emoji
from bot.handlers import (
    start, shop, wallet, profile, freebies, referral, membership, admin, support,
    force_join, admin_extra,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# How often the background task re-applies admin command scopes (seconds).
# Ensures menus stay correct if Telegram resets scopes or ADMIN_IDS is updated
# via an external mechanism while the process is running.
ADMIN_SYNC_INTERVAL: int = 3600  # 1 hour


async def periodic_admin_sync(bot, interval: int = ADMIN_SYNC_INTERVAL) -> None:
    """Background task: re-apply admin command scopes every *interval* seconds.

    Admin IDs are re-fetched from the DB on every tick so that changes made
    via bot commands (or any external DB write) take effect without a restart.
    The in-memory ``bot.config.ADMIN_IDS`` list is updated in-place on each tick
    so that all synchronous ``is_admin()`` checks stay aligned with the DB source.
    The loop runs until cancelled (e.g. on shutdown).
    """
    while True:
        await asyncio.sleep(interval)
        try:
            current_ids = await get_admin_ids()
            # Mutate the shared list in-place so every is_admin() check that
            # reads bot.config.ADMIN_IDS picks up the change immediately.
            _config.ADMIN_IDS[:] = current_ids
            await sync_admin_commands(bot, current_ids)
            logger.info("Periodic admin command sync completed.")
        except Exception as e:
            logger.warning(f"Periodic admin sync failed: {e}")


async def sync_admin_commands(bot, admin_ids: List[int]) -> None:
    """Diff admin IDs against the previously persisted set and update Telegram
    command menus accordingly.

    - Admins no longer in *admin_ids* have their scoped commands cleared.
    - All admins in *admin_ids* receive the full admin command set.
    - The new set is persisted to the DB so the next restart can diff against it.
    """
    common_commands = [
        BotCommand(command="start",  description="Open the main menu"),
        BotCommand(command="menu",   description="Open the main menu"),
        BotCommand(command="admin",  description="Open the admin panel"),
    ]
    admin_commands = common_commands + [
        BotCommand(command="restock",      description="Upload stock for a product · /restock <id>"),
        BotCommand(command="setlowstock",  description="View or set the low-stock alert threshold · /setlowstock <n>"),
    ]

    # Load previously known admin IDs so we can clear commands for removed admins
    prev_admin_ids_str = await get_setting("known_admin_ids")
    prev_admin_ids: set[int] = set()
    if prev_admin_ids_str:
        for x in prev_admin_ids_str.split(","):
            x = x.strip()
            if x.isdigit():
                prev_admin_ids.add(int(x))

    current_admin_ids: set[int] = set(admin_ids)
    removed_admin_ids = prev_admin_ids - current_admin_ids

    # Clear commands for admins that have been removed
    for admin_id in removed_admin_ids:
        try:
            await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=admin_id))
            logger.info(f"Cleared admin commands for removed admin {admin_id}")
        except Exception as e:
            logger.warning(f"Could not clear commands for removed admin {admin_id}: {e}")

    # Set admin commands for all current admins
    for admin_id in admin_ids:
        try:
            await bot.set_my_commands(
                commands=admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
            logger.info(f"Set admin commands for user {admin_id}")
        except Exception as e:
            logger.warning(f"Could not set commands for admin {admin_id}: {e}")

    # Persist the current admin list so the next restart can diff against it
    await set_setting("known_admin_ids", ",".join(str(i) for i in admin_ids))


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Add it as a Railway variable named BOT_TOKEN.")
        sys.exit(1)

    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready.")

    # Load admin-configured premium (custom) emoji IDs
    await refresh_premium_emoji()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    try:
        info = await bot.get_me()
        os.environ["BOT_USERNAME"] = info.username or ""
        logger.info(f"Bot: @{info.username} ({info.full_name})")
    except Exception as e:
        logger.error(f"Failed to get bot info: {e}")
        sys.exit(1)

    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())
    # Force-join gate (no-op while disabled in the admin panel)
    dp.message.middleware(ForceJoinMiddleware())
    dp.callback_query.middleware(ForceJoinMiddleware())

    # Routers — order matters for catch-all handlers
    dp.include_router(force_join.router)
    dp.include_router(start.router)
    dp.include_router(shop.router)
    dp.include_router(wallet.router)
    dp.include_router(profile.router)
    dp.include_router(freebies.router)
    dp.include_router(referral.router)
    dp.include_router(membership.router)
    dp.include_router(support.router)
    dp.include_router(admin.router)
    dp.include_router(admin_extra.router)

    # Default commands visible to all users
    common_commands = [
        BotCommand(command="start",  description="Open the main menu"),
        BotCommand(command="menu",   description="Open the main menu"),
        BotCommand(command="admin",  description="Open the admin panel"),
    ]
    try:
        await bot.set_my_commands(common_commands)
    except Exception as e:
        logger.warning(f"Could not set default commands: {e}")

    # Seed the live admin ID list only when the DB setting is absent (first boot).
    # On subsequent boots the DB-managed value is preserved, so admins added or
    # removed via bot commands are not silently overwritten.
    await seed_admin_ids(ADMIN_IDS)

    # Diff against previous run and update per-admin command scopes
    await sync_admin_commands(bot, ADMIN_IDS)

    logger.info("=" * 50)
    logger.info("  🤖 PremiumShop Bot is ONLINE")
    logger.info("=" * 50)

    # Background task: keep admin command scopes in sync while the bot runs.
    # Admin IDs are re-read from the DB each tick, so changes applied via bot
    # commands (or external DB writes) take effect without a restart.
    sync_task = asyncio.create_task(periodic_admin_sync(bot))

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    except Exception as e:
        logger.error(f"Fatal: {e}", exc_info=True)
        sys.exit(1)
