# handlers/private_chat.py
# Sud Tizimi — Lichka (shaxsiy chat) handlerlari
#
# MUHIM TUZATISH: Bu fayldan barcha DO'KON bilan bog'liq handlerlar
# (/shop, xarid qilish, /mening_xaridlarim) OLIB TASHLANDI, chunki
# ular endi handlers/shop.py da to'liq va kengaytirilgan holda mavjud.
#
# Ilgari ikkala fayl ham bir xil "/shop" buyrug'ini va bir-biriga
# o'xshash (lekin nomlari boshqa) callback'larni ushlardi:
#   - private_chat.py: "buy_", "confirm_buy_"
#   - shop.py:          "shop_buy_", "shop_confirm_"
# Bu ikkita mustaqil, bir-biridan bexabar do'kon tizimini yaratib,
# foydalanuvchi qaysi versiyasiga tegishi tasodifga bog'liq bo'lib
# qolardi (aiogram'da bitta buyruqni bir nechta router ushlasa,
# faqat birinchisi javob beradi — bu sokin, ko'rinmas bug edi).
#
# Endi do'kon MANTIG'I FAQAT shop.py da yashaydi.

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from config import ADMIN_ID
from database.db_main import register_user, get_user, get_coins

router = Router()


# ─────────────────────────────────────────────────────
#  /start — Lichkada salomlashish
# ─────────────────────────────────────────────────────

@router.message(Command("start"), F.chat.type == "private")
async def cmd_start_private(message: Message):
    await register_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )
    user = await get_user(message.from_user.id)
    coins = user["coins"] if user else 0

    text = (
        "👤 <b>SUD TIZIMI</b> botiga xush kelibsiz!\n\n"
        f"💰 Balansingiz: <b>{coins} Court Coins</b>\n\n"
        "📜 <b>Mavjud buyruqlar:</b>\n"
        "🛒 /shop – Do'kon (super kartalar)\n"
        "📦 /inventar – Faol kartalarim\n"
        "📦 /mening_xaridlarim – Xaridlar tarixi\n"
        "📝 /ariza [sabab] – Sudyaga ariza yuborish\n"
        "💰 /balans – Coin balansim\n\n"
        "🏛️ O'yinni boshlash uchun guruhda <code>/yangi_ish</code> yozing!\n"
        "🤖 Yordam uchun bot adminiga murojat qiling : [@dasturchi_uzn1]\n\n"
        "Bizning asosiy guruhimiz kirib o'yinga qo'shiling : https://t.me/sudlashamizmi "
    )

    if message.from_user.id == ADMIN_ID:
        text += "\n\n⚙️ /add_item – Yangi tovar qo'shish (Admin)"

    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────────────
#  /balans — Coin balansi
# ─────────────────────────────────────────────────────

@router.message(Command("balans"), F.chat.type == "private")
async def cmd_balans(message: Message):
    await register_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )
    coins = await get_coins(message.from_user.id)
    await message.answer(
        f"💰 <b>Sizning balansingiz:</b>\n\n"
        f"🏅 <b>{coins} Court Coins</b>\n\n"
        f"O'yinda g'alaba qozonib coin to'plang va /shop da sarflang!",
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────
#  /ariza — Sudyaga ariza yuborish
#  (Matnli rejimda yoki ovozsiz qolib ketganda yozma ruxsat so'rash)
# ─────────────────────────────────────────────────────

@router.message(Command("ariza"), F.chat.type == "private")
async def cmd_ariza(message: Message, bot: Bot):
    from database.db_main import (
        get_active_game, get_player, check_ariza_cooldown,
        update_ariza_cooldown, save_ariza
    )

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "📝 <b>Ariza yozish:</b>\n\n"
            "Foydalanish: <code>/ariza [sabab]</code>\n\n"
            "Misol: <code>/ariza Internetim yo'q, yozma gapira olaman</code>\n\n"
            "<i>Eslatma: Ariza yuborish uchun avval o'yin guruhida "
            "qaysi o'yinda ekaningizni bot bilishi kerak. Agar javob "
            "kelmasa, guruhda faol o'yinda ekaningizni tekshiring.</i>",
            parse_mode="HTML"
        )
        return

    # Spam oldini olish — 60 soniya cooldown
    can_send = await check_ariza_cooldown(message.from_user.id, 60)
    if not can_send:
        await message.answer(
            "⏳ Arizani qayta yuborish uchun <b>60 soniya</b> kutishingiz kerak.",
            parse_mode="HTML"
        )
        return

    ariza_text = args[1].strip()
    await update_ariza_cooldown(message.from_user.id)

    await message.answer(
        "⏳ Arizangiz yuborildi. Sudya javobini kuting.\n\n"
        "<i>Eslatma: Ariza faqat siz qatnashayotgan FAOL o'yin guruhiga yuboriladi. "
        "Agar bir nechta guruhda o'ynayotgan bo'lsangiz, har biriga alohida murojaat qiling.</i>",
        parse_mode="HTML"
    )
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

# config.py faylida ADMIN_ID o'zgaruvchisi bor deb hisoblaymiz
from config import ADMIN_ID 
# db.py faylidagi bazani yangilash funksiyasi (loyihangizga qarab nomlang)
from database.db_main import add_coins


router = Router()

@router.message(Command("add_coin"))
async def add_coin_for_admin(message: Message):
    # Faqat siz ishlata olishingiz uchun tekshiruv
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Bu buyruq faqat bot admini uchun!")
        return

    # Buyruq formati: /add_coin 5000
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("⚠️ Miqdorni kiriting. Misol: `/add_coin 5000`")
            return
            
        amount = int(args[1])
        
        # Bazada balansni yangilash (O'z ma'lumotlar bazasi funksiyangizga moslang)
        # users jadvalidagi balansni yangilaydi
        await update_user_balance(message.from_user.id, amount)
        
        await message.answer(f"✅ Hisobingizga muvaffaqiyatli {amount} Court Coins qo'shildi!")
        
    except ValueError:
        await message.answer("❌ Miqdor faqat son bo'lishi kerak!")
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {str(e)}")
    # Eslatma: Real ariza yo'naltirish guruh-darajasida ishlaydi —
    # group_chat.py dagi /arz_sudya va Sudyaning tasdiqlash panellari orqali.
    # Bu yerda faqat matnni saqlab qo'yamiz, Sudya buni qo'lda ko'rishi kerak
    # bo'lsa, guruhda alohida ko'rsatish mantig'i qo'shilishi mumkin.


# ─────────────────────────────────────────────────────
#  /add_item — Admin: yangi tovar qo'shish
#  (Eslatma: bu funksiya endi handlers/shop.py da ham mavjud va
#  to'liqroq ishlaydi — bu yerda faqat orqaga moslik uchun qoldirilgan)
# ─────────────────────────────────────────────────────
# MUHIM: Bu handler shop.py dagi bilan TO'QNASHMASLIGI uchun olib
# tashlandi. /add_item endi FAQAT handlers/shop.py da ishlaydi.
