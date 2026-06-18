import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database.db_main import create_tables
# shop modulini ham import qilamiz (agar u mavjud bo'lsa)
from handlers import group_chat, private_chat
try:
    from handlers import shop
except ImportError:
    shop = None

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

    # 3. Handlerlarni ulash (Tartib juda muhim!)
    dp.include_router(group_chat.router)
    dp.include_router(private_chat.router)
    
    # Do'kon routerini ulash
    if shop and hasattr(shop, "router"):
        dp.include_router(shop.router)
        logger.info("Do'kon (shop.py) routeri muvaffaqiyatli ulandi.")

    # 4. Botni ishga tushirish
    logger.info("Bot ishga tushmoqda... 🚀")
    try:
        # Xatolikni yo'qotish uchun barcha update turlarini ochiqchasiga qabul qilamiz
        await dp.start_polling(
            bot, 
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"]
        )
    finally:
        await bot.session.close()
        logger.info("Bot to'xtatildi.")


if __name__ == "__main__":
    asyncio.run(main())
