# main.py

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database.db_main import create_tables
from handlers import group_chat, private_chat

# Loglarni yoqish
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    # 1. Jadvallarni yaratish
    logger.info("Ma'lumotlar bazasi tayyorlanmoqda...")
    await create_tables()
    logger.info("Jadvallar tayyor!")

    # 2. Bot va Dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # 3. Handlerlarni ulash
    dp.include_router(group_chat.router)
    dp.include_router(private_chat.router)

    # 4. Botni ishga tushirish
    logger.info("Bot ishga tushmoqda... 🚀")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("Bot to'xtatildi.")


if __name__ == "__main__":
    asyncio.run(main())