"""Entry point."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import Update

import db
from bot import register
from config import BOT_TOKEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    register(dp, bot)

    await db.init_db()
    logger.info("Bot started. Polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
