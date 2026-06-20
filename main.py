# main.py
# Sud Tizimi Bot — Kirish nuqtasi

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database.db_main import create_tables
from handlers import group_chat, private_chat, shop
from handlers.shop import seed_shop_items

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

    # 2. Do'kon tovarlarini DB'ga seed qilish
    # (handlers/shop.py dagi SHOP_ITEMS dict'idan avtomatik yuklanadi)
    logger.info("Do'kon tovarlari tekshirilmoqda...")
    await seed_shop_items()
    logger.info("Do'kon tayyor!")

    # 3. Bot va Dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # 4. Handlerlarni ulash
    # MUHIM: group_chat dan oldin shop ulanadi, chunki shop.py dagi
    # ba'zi matn-based handlerlar (!jamoa_send, !insayd_send, !bribe)
    # faqat private chatda ishlaydi va group_chat bilan ziddiyat qilmaydi,
    # lekin tartib aiogram'da handler ustuvorligiga ta'sir qiladi.
    dp.include_router(shop.router)
    dp.include_router(group_chat.router)
    dp.include_router(private_chat.router)

    # 5. Botni ishga tushirish
    logger.info("Bot ishga tushmoqda... 🚀")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("Bot to'xtatildi.")


if __name__ == "__main__":
    asyncio.run(main())
