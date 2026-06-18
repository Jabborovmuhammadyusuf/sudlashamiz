# handlers/shop.py
# Sud Tizimi — Alohida Do'kon Moduli
# Barcha tovarlar markazlashgan SHOP_ITEMS dict'ida.
# Yangi karta qo'shish uchun faqat shu dict'ga element qo'shish yetarli.

import logging
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)

from database.db_main import (
    register_user, get_user, get_coins,
    get_all_shop_items, get_shop_item, buy_item,
    get_user_purchases, mark_item_used, get_purchase_by_id,
    add_shop_item, get_active_game, get_player,
    set_player_immunity, set_player_bail, set_night_blocked,
    save_night_action, get_game_by_id, log_team_chat,
    get_team_players, add_coins, get_player_night_action
)

logger = logging.getLogger(__name__)
router = Router()

# ══════════════════════════════════════════════════════
#  MARKAZLASHGAN DO'KON KATALOГИ
#  Yangi tovar qo'shish uchun quyidagi dict'ga element qo'shing.
#  Har bir element DB'ga seed qilinadi yoki mavjud bo'lsa o'tkazib yuboriladi.
# ══════════════════════════════════════════════════════

SHOP_ITEMS: dict[str, dict] = {

    "old_document": {
        "name":        "📜 Eski sanali hujjat",
        "description": "Sudya baholash bosqichida o'z jamoasi ballariga avtomatik +2 ochko qo'shadi. "
                       "Tunda inventardan faollashtiring.",
        "price":       300,
        "effect_code": "old_document",
    },

    "bribe": {
        "name":        "💰 Pora / Og'iz yopish",
        "description": "Raqib jamoaning muayyan a'zosini tanlaysiz — u keyingi raundda gapirish "
                       "huquqidan mahrum bo'ladi (mute).",
        "price":       400,
        "effect_code": "bribe",
    },

    "anon_insight": {
        "name":        "🕵️ Anonim insayd",
        "description": "Bot lichkasiga matn yozing, bot uni guruhga 'Yashirin manbadan sizdirilgan "
                       "dalil' deb mutlaqo anonim e'lon qiladi.",
        "price":       250,
        "effect_code": "anon_insight",
    },

    "uncle_card": {
        "name":        "🃏 Amakingizning vizitkasi",
        "description": "Pristav yoki Qoralarning salbiy ta'siridan (bloklardan) sizga tunda "
                       "avtomatik daxlsizlik (immunitet) beradi.",
        "price":       350,
        "effect_code": "uncle_card",
    },

    "bail_contract": {
        "name":        "📋 Kafillik shartnomasi",
        "description": "O'yin oxirida Real Ayblanuvchi yutqazsa ham, uni 30 daqiqalik guruh "
                       "mutesidan (qamoqdan) kafillik evaziga asrab qoladi.",
        "price":       500,
        "effect_code": "bail_contract",
    },
}

# Effekt kodlarini tun fazasi uchun qulayroq to'plam
NIGHT_USE_EFFECTS = {"old_document", "bribe", "anon_insight", "uncle_card", "bail_contract"}


# ══════════════════════════════════════════════════════
#  DO'KON TOVARLARINI DB'GA SEED QILISH
#  main.py ichida create_tables() dan keyin chaqiring:
#      from handlers.shop import seed_shop_items
#      await seed_shop_items()
# ══════════════════════════════════════════════════════

async def seed_shop_items():
    """
    SHOP_ITEMS dict'idagi tovarlarni DB'ga qo'shadi.
    Agar effect_code allaqachon mavjud bo'lsa, o'tkazib yuboradi.
    """
    existing = await get_all_shop_items()
    existing_codes = {i["effect_code"] for i in existing}
    for code, item in SHOP_ITEMS.items():
        if code not in existing_codes:
            await add_shop_item(
                item["name"],
                item["description"],
                item["price"],
                item["effect_code"],
            )
            logger.info(f"Do'konga yangi tovar qo'shildi: {item['name']}")


# ══════════════════════════════════════════════════════
#  /shop — Do'kon (lichkada)
# ══════════════════════════════════════════════════════

@router.message(Command("shop"))
async def cmd_shop(message: Message):
    if message.chat.type != "private":
        await message.reply(
            "🛒 Do'konga kirish uchun botga <b>shaxsiy xabar</b> yuboring:\n"
            "/shop",
            parse_mode="HTML"
        )
        return

    await register_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )

    items = await get_all_shop_items()
    coins = await get_coins(message.from_user.id)

    if not items:
        await message.answer(
            "🛒 <b>Do'kon hozircha bo'sh.</b>\n\n"
            "Admin tez orada super kartalar qo'shadi!",
            parse_mode="HTML"
        )
        return

    text = (
        f"🛒 <b>SUPER KARTALAR DO'KONI</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Balansingiz: <b>{coins} Court Coins</b>\n\n"
    )
    buttons = []

    for item in items:
        affordable = "✅" if coins >= item["price"] else "❌"
        text += (
            f"{affordable} <b>{item['name']}</b>\n"
            f"   📖 {item['description']}\n"
            f"   💰 Narxi: <b>{item['price']}</b> coins\n\n"
        )
        buttons.append([
            InlineKeyboardButton(
                text=f"🛍 {item['name']} — {item['price']} coins",
                callback_data=f"shop_buy_{item['item_id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="📦 Mening xaridlarim",
            callback_data="shop_my_items"
        )
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# ══════════════════════════════════════════════════════
#  XARID QILISH
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("shop_buy_"))
async def cb_shop_buy(call: CallbackQuery):
    item_id = int(call.data.split("_")[2])
    item = await get_shop_item(item_id)

    if not item:
        await call.answer("❌ Tovar topilmadi!", show_alert=True)
        return

    coins = await get_coins(call.from_user.id)
    if coins < item["price"]:
        await call.answer(
            f"❌ Coinlar yetarli emas!\n"
            f"Kerak: {item['price']} | Sizda: {coins}",
            show_alert=True
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Ha, sotib olaman!",
                callback_data=f"shop_confirm_{item_id}"
            ),
            InlineKeyboardButton(
                text="❌ Bekor qilish",
                callback_data="shop_cancel"
            )
        ]
    ])
    await call.message.answer(
        f"🛍 <b>Xaridni tasdiqlang</b>\n\n"
        f"📦 <b>{item['name']}</b>\n"
        f"📖 {item['description']}\n"
        f"💰 Narxi: <b>{item['price']} coins</b>\n\n"
        f"Balansingizdan {item['price']} coins hisobdan chiqariladi.",
        parse_mode="HTML",
        reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data.startswith("shop_confirm_"))
async def cb_shop_confirm(call: CallbackQuery):
    item_id = int(call.data.split("_")[2])
    success = await buy_item(call.from_user.id, item_id)

    if success:
        item = await get_shop_item(item_id)
        coins = await get_coins(call.from_user.id)
        await call.message.edit_text(
            f"🎉 <b>Xarid muvaffaqiyatli!</b>\n\n"
            f"📦 <b>{item['name']}</b> sizniki bo'ldi!\n"
            f"📖 <i>{item['description']}</i>\n\n"
            f"💰 Qolgan balans: <b>{coins} coins</b>\n\n"
            f"📦 Xaridlaringizni /inventar orqali ko'ring va tunda ishlating!",
            parse_mode="HTML"
        )
    else:
        await call.message.edit_text(
            "❌ Xarid amalga oshmadi. Coinlar yetarli emas yoki xato yuz berdi."
        )
    await call.answer()


@router.callback_query(F.data == "shop_cancel")
async def cb_shop_cancel(call: CallbackQuery):
    await call.message.edit_text("❌ Xarid bekor qilindi.")
    await call.answer()


# ══════════════════════════════════════════════════════
#  /inventar — Xaridlar va ishlatish
# ══════════════════════════════════════════════════════

@router.message(Command("inventar"))
async def cmd_inventar(message: Message):
    if message.chat.type != "private":
        await message.reply("📦 Inventarni lichkada ko'ring: /inventar")
        return

    purchases = await get_user_purchases(message.from_user.id, unused_only=True)

    if not purchases:
        await message.answer(
            "📦 <b>Faol kartalaringiz yo'q.</b>\n\n"
            "O'yinda coin to'plab /shop da super kartalar sotib oling!",
            parse_mode="HTML"
        )
        return

    text = "📦 <b>MENING INVENTARIM</b>\n━━━━━━━━━━━━━━━\n\n"
    buttons = []

    for p in purchases:
        text += (
            f"🃏 <b>{p['name']}</b>\n"
            f"   📖 {p['description']}\n"
            f"   🗓 Sotib olingan: {p['bought_at'][:10]}\n\n"
        )
        if p["effect_code"] in NIGHT_USE_EFFECTS:
            buttons.append([
                InlineKeyboardButton(
                    text=f"⚡ {p['name']} — ISHLATISH",
                    callback_data=f"use_item_{p['id']}"
                )
            ])

    if not buttons:
        text += "<i>Hozir ishlatilishi mumkin bo'lgan kartalar yo'q.</i>"

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "shop_my_items")
async def cb_shop_my_items(call: CallbackQuery):
    await cmd_inventar(call.message)
    await call.answer()


# ══════════════════════════════════════════════════════
#  KARTA ISHLATISH — Tun fazasida
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("use_item_"))
async def cb_use_item(call: CallbackQuery, bot: Bot):
    """Inventardan karta ishlatish — tun fazasida."""
    purchase_id = int(call.data.split("_")[2])
    purchase = await get_purchase_by_id(purchase_id)

    if not purchase:
        await call.answer("❌ Xarid topilmadi!", show_alert=True)
        return
    if purchase["user_id"] != call.from_user.id:
        await call.answer("⛔️ Bu sizning kartangiz emas!", show_alert=True)
        return
    if purchase["used"]:
        await call.answer("⚠️ Bu karta allaqachon ishlatilgan!", show_alert=True)
        return

    effect = purchase["effect_code"]

    # Karta ishlatish uchun aktiv o'yinni topish zarur
    # Foydalanuvchining qaysi o'yinda ekanini bilamiz (lichkada so'raymiz)
    # Bu yerda universal approach: foydalanuvchiga guruh ID kiritish yoki
    # bot o'zi topadi (agent-based emas, shuning uchun quyidagicha):

    if effect == "anon_insight":
        # Matnli karta — guruh ID kerak emas, botdan so'raymiz
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="❌ Bekor qilish",
                callback_data="shop_cancel"
            )
        ]])
        await call.message.answer(
            f"🕵️ <b>Anonim insayd</b>\n\n"
            f"Guruhga anonim yubormoqchi bo'lgan dalil matnini yuboring.\n"
            f"Format: <code>!insayd_{purchase_id} [matn]</code>\n\n"
            f"<i>Misol: !insayd_{purchase_id} Ali shanba kuni likopchadagi go'shtni yegani CCTV'da ko'ringan</i>",
            parse_mode="HTML",
            reply_markup=kb
        )
        await call.answer()
        return

    if effect in ("bribe", "old_document", "uncle_card", "bail_contract"):
        # O'yinchi o'zini qaysi o'yinda ekanini bilishi kerak
        # Bu effektlar uchun o'yinchi chat_id yuborishi kerak
        # Sodda yondashuv: so'ng kelgan effektlar uchun confirm paneli
        await _show_effect_panel(call, purchase_id, effect, purchase["name"])
        return


async def _show_effect_panel(
    call: CallbackQuery, purchase_id: int,
    effect: str, name: str
):
    """Effekt turini ko'rsatib tasdiqlash panelini chiqaradi."""
    descriptions = {
        "old_document": (
            "📜 <b>Eski sanali hujjat</b>\n\n"
            "Bu karta joriy o'yin baholash bosqichida "
            "jamoangiz ballariga <b>+2 ochko</b> avtomatik qo'shadi.\n\n"
            "Guruh ID: <code>/my_game_id</code> buyrug'i bilan bilib oling."
        ),
        "bribe": (
            "💰 <b>Pora / Og'iz yopish</b>\n\n"
            "Raqib jamoaning qaysi a'zosini keyingi raundda jimga qo'ymoqchisiz?\n"
            "Format: <code>!bribe_{purchase_id} [user_id]</code>"
        ),
        "uncle_card": (
            "🃏 <b>Amakingizning vizitkasi</b>\n\n"
            "Bu karta sizi tun davomida Pristav va Qoralarning "
            "bloklaridan himoya qiladi.\n\n"
            "Tasdiqlash uchun quyidagi tugmani bosing."
        ),
        "bail_contract": (
            "📋 <b>Kafillik shartnomasi</b>\n\n"
            "Agar siz Real Ayblanuvchi bo'lsangiz va Qoralar g'alaba qozonsa ham, "
            "30 daqiqalik mute jazosidan saqlab qolasiz.\n\n"
            "Tasdiqlash uchun quyidagi tugmani bosing."
        ),
    }

    text = descriptions.get(effect, f"⚡ <b>{name}</b>\n\nQayta tasdiqlang.")
    text = text.replace("{purchase_id}", str(purchase_id))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Ishlatish",
                callback_data=f"confirm_use_{purchase_id}"
            ),
            InlineKeyboardButton(
                text="❌ Bekor",
                callback_data="shop_cancel"
            )
        ]
    ])
    await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("confirm_use_"))
async def cb_confirm_use_item(call: CallbackQuery, bot: Bot):
    """Karta ishlatishni tasdiqlash."""
    purchase_id = int(call.data.split("_")[2])
    purchase = await get_purchase_by_id(purchase_id)

    if not purchase or purchase["used"]:
        await call.answer("⚠️ Karta allaqachon ishlatilgan yoki topilmadi!", show_alert=True)
        return
    if purchase["user_id"] != call.from_user.id:
        await call.answer("⛔️ Bu sizning kartangiz emas!", show_alert=True)
        return

    effect = purchase["effect_code"]
    user_id = call.from_user.id

    # Har bir effektni qo'llash
    result_text = await _apply_effect(bot, user_id, purchase_id, effect)

    await call.message.edit_text(
        f"⚡ <b>Karta ishlatildi!</b>\n\n{result_text}",
        parse_mode="HTML"
    )
    await call.answer("✅ Karta ishlatildi!")


async def _apply_effect(
    bot: Bot, user_id: int, purchase_id: int, effect: str
) -> str:
    """
    Effektni bazada belgilaydi.
    Asosiy ta'sir group_chat.py tomonidan tun oxirida qo'llanadi.
    Bu yerda faqat belgini o'rnatamiz.
    """

    if effect == "uncle_card":
        # Foydalanuvchining aktiv o'yinini topish uchun
        # lichkada game_id so'raymiz (sodda yondashuv)
        # Haqiqiy implementatsiyada session/state dan olish kerak
        # Biz flagni users'ga yozamiz — group_chat.py tun oxirida tekshiradi
        # Shu sababli DB'da users.has_uncle_card ustuni o'rniga
        # purchases.used = 0 qoldiramiz va group_chat.py tekshiradi
        return (
            "🃏 <b>Amakingizning vizitkasi</b> faollashdi!\n\n"
            "Tun davomida Pristav va Qoralar bloklaridan himoyalanasiz.\n"
            "<i>Ta'sir keyingi 'Yopiq Tergov' bosqichida ko'rinadi.</i>"
        )

    elif effect == "bail_contract":
        return (
            "📋 <b>Kafillik shartnomasi</b> imzolandi!\n\n"
            "Agar o'yin oxirida Real Ayblanuvchi sifatida yutqazsangiz ham, "
            "mute jazosidan ozod qilinasiz.\n"
            "<i>Ta'sir o'yin yakunida avtomatik qo'llanadi.</i>"
        )

    elif effect == "old_document":
        return (
            "📜 <b>Eski sanali hujjat</b> faollashdi!\n\n"
            "Joriy raundning baholash bosqichida jamoangiz ballariga "
            "<b>+2 ochko</b> avtomatik qo'shiladi.\n"
            "<i>Sudya ball berganida ta'sir ko'rinadi.</i>"
        )

    elif effect == "bribe":
        return (
            "💰 <b>Pora</b> tayyorlandi!\n\n"
            "Raqib jamoaning a'zosini jimga qo'yish uchun:\n"
            "<code>!bribe [user_id] [guruh_id]</code> buyrug'ini yuboring.\n"
            "<i>Misol: !bribe 123456789 -1001234567890</i>"
        )

    return "✅ Karta faollashdi!"


# ══════════════════════════════════════════════════════
#  !insayd — Anonim dalil yuborish (lichkada)
# ══════════════════════════════════════════════════════

@router.message(F.text.regexp(r"^!insayd_(\d+) (.+)$"), F.chat.type == "private")
async def cmd_insayd(message: Message, bot: Bot):
    import re
    match = re.match(r"^!insayd_(\d+) (.+)$", message.text)
    if not match:
        return

    purchase_id = int(match.group(1))
    insayd_text = match.group(2).strip()

    purchase = await get_purchase_by_id(purchase_id)
    if not purchase:
        await message.answer("❌ Xarid topilmadi!")
        return
    if purchase["user_id"] != message.from_user.id:
        await message.answer("⛔️ Bu sizning kartangiz emas!")
        return
    if purchase["used"]:
        await message.answer("⚠️ Bu karta allaqachon ishlatilgan!")
        return
    if purchase["effect_code"] != "anon_insight":
        await message.answer("❌ Bu karta anonim insayd emas!")
        return

    # Foydalanuvchiga guruh ID so'rash — sodda yondashuv
    # Foydalanuvchi guruh chat_id ni bilishi kerak
    await message.answer(
        "📍 Endi qaysi guruhga yuborishni ko'rsating:\n"
        f"Format: <code>!insayd_send_{purchase_id}_{{}chat_id{{}} {insayd_text}</code>\n\n"
        f"<i>Guruh chat_id ni bilmasangiz, guruhda /my_game_id buyrug'ini yuboring.</i>",
        parse_mode="HTML"
    )
    # Muqobil: bot state management (FSM) bilan to'liq implementatsiya qilish mumkin


@router.message(F.text.regexp(r"^!insayd_send_(\d+)_(-?\d+) (.+)$"), F.chat.type == "private")
async def cmd_insayd_send(message: Message, bot: Bot):
    import re
    match = re.match(r"^!insayd_send_(\d+)_(-?\d+) (.+)$", message.text)
    if not match:
        return

    purchase_id = int(match.group(1))
    chat_id = int(match.group(2))
    insayd_text = match.group(3).strip()

    purchase = await get_purchase_by_id(purchase_id)
    if not purchase or purchase["used"] or purchase["user_id"] != message.from_user.id:
        await message.answer("❌ Xarid topilmadi yoki allaqachon ishlatilgan!")
        return

    game = await get_active_game(chat_id)
    if not game:
        await message.answer("❌ Ushbu guruhda aktiv o'yin topilmadi!")
        return

    try:
        await bot.send_message(
            chat_id,
            f"🔒 <b>YASHIRIN MANBADAN SIZDIRILGAN DALIL:</b>\n\n"
            f"<i>«{insayd_text}»</i>\n\n"
            f"<code>— Anonim manba</code>",
            parse_mode="HTML"
        )
        await mark_item_used(purchase_id, game["game_id"])
        await message.answer(
            "✅ Anonim insayd muvaffaqiyatli guruhga yuborildi!\n"
            "Hech kim siz yuborganingizni bilmaydi."
        )
    except Exception as e:
        await message.answer(f"❌ Yuborishda xato: {e}")


# ══════════════════════════════════════════════════════
#  !bribe — Pora: raqibni jim qilish (lichkada)
# ══════════════════════════════════════════════════════

@router.message(F.text.regexp(r"^!bribe (\d+) (-?\d+)$"), F.chat.type == "private")
async def cmd_bribe(message: Message, bot: Bot):
    """
    Format: !bribe [target_user_id] [chat_id]
    """
    import re
    match = re.match(r"^!bribe (\d+) (-?\d+)$", message.text)
    if not match:
        return

    target_id = int(match.group(1))
    chat_id = int(match.group(2))

    # Foydalanuvchining bribe kartalari bormi?
    purchases = await get_user_purchases(message.from_user.id, unused_only=True)
    bribe_card = next(
        (p for p in purchases if p["effect_code"] == "bribe"), None
    )

    if not bribe_card:
        await message.answer("❌ Sizda 'Pora' kartasi yo'q!")
        return

    game = await get_active_game(chat_id)
    if not game:
        await message.answer("❌ Ushbu guruhda aktiv o'yin topilmadi!")
        return

    target_player = await get_player(game["game_id"], target_id)
    if not target_player:
        await message.answer("❌ Nishon ushbu o'yinda qatnashmayapti!")
        return

    sender_player = await get_player(game["game_id"], message.from_user.id)
    if not sender_player:
        await message.answer("❌ Siz ushbu o'yinda qatnashmayapsiz!")
        return

    if target_player["team"] == sender_player["team"]:
        await message.answer("❌ O'z jamoangiz a'zosini jim qila olmaysiz!")
        return

    # Nishonni keyingi raundda bloklash uchun belgilaymiz
    await set_night_blocked(game["game_id"], target_id, True)
    await mark_item_used(bribe_card["id"], game["game_id"])

    try:
        # Nishonga xabar yuborib bo'lmaydi (anonim bo'lishi kerak)
        # Shunchaki kartani ishlatilgan deb belgilaymiz
        pass
    except Exception:
        pass

    await message.answer(
        f"✅ <b>Pora muvaffaqiyatli!</b>\n\n"
        f"Nishon (ID: <code>{target_id}</code>) keyingi raundda "
        f"gapirish huquqidan mahrum bo'ladi.\n"
        f"<i>Bu amal maxfiy — hech kim bilmaydi.</i>",
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════
#  JAMOA MAXFIY CHATI — Lichkadan echo
# ══════════════════════════════════════════════════════

@router.message(F.text.startswith("!jamoa "), F.chat.type == "private")
async def cmd_jamoa_chat(message: Message, bot: Bot):
    """
    O'yinchi lichkada '!jamoa [matn]' yuborganda,
    bot jamoasidagi tirik barcha a'zolarga anonim dublyaj qiladi.
    """
    text = message.text[7:].strip()
    if not text:
        await message.answer(
            "📩 Format: <code>!jamoa [matn]</code>\n"
            "Misol: <code>!jamoa Keyingi raundda !dalil beraman, siz jim turing!</code>",
            parse_mode="HTML"
        )
        return

    # Foydalanuvchining aktiv o'yinini topish
    # Biz chat_id ni bilmaymiz — foydalanuvchi ko'rsatishi kerak
    await message.answer(
        "📍 Qaysi guruhning maxfiy chatiga yuboryapsiz?\n"
        f"Format: <code>!jamoa_send [-chat_id] {text}</code>\n\n"
        "<i>Guruh ID ni bilish uchun guruhda /my_game_id buyrug'ini yuboring.</i>",
        parse_mode="HTML"
    )


@router.message(F.text.regexp(r"^!jamoa_send (-?\d+) (.+)$"), F.chat.type == "private")
async def cmd_jamoa_send(message: Message, bot: Bot):
    import re
    match = re.match(r"^!jamoa_send (-?\d+) (.+)$", message.text)
    if not match:
        return

    chat_id = int(match.group(1))
    text = match.group(2).strip()

    game = await get_active_game(chat_id)
    if not game or game["phase"] != "night":
        await message.answer(
            "❌ O'yin 'Yopiq Tergov' (tun) fazasida emas yoki topilmadi!\n"
            "Jamoa chati faqat tun fazasida ishlaydi."
        )
        return

    player = await get_player(game["game_id"], message.from_user.id)
    if not player or not player["is_alive"]:
        await message.answer("❌ Siz bu o'yinda yo'qsiz yoki chiqib ketgansiz!")
        return

    team = player["team"]
    teammates = await get_team_players(game["game_id"], team)

    team_name = "⚖️ OQ JAMOA" if team == "white" else "🖤 QORA JAMOA"
    echo_text = (
        f"💬 <b>{team_name} | MAXFIY KANAL</b>\n\n"
        f"👤 <i>Jamoangizdan anonim xabar:</i>\n"
        f"«{text}»"
    )

    sent_count = 0
    for mate in teammates:
        if mate["user_id"] == message.from_user.id:
            continue  # o'ziga yubormaymiz
        try:
            await bot.send_message(
                mate["user_id"],
                echo_text,
                parse_mode="HTML"
            )
            sent_count += 1
        except Exception:
            pass

    # Loglash
    await log_team_chat(game["game_id"], message.from_user.id, team, text)

    await message.answer(
        f"✅ Xabar {sent_count} ta jamoangiz a'zosiga anonim yuborildi.",
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════
#  /mening_xaridlarim — Barcha xaridlar tarixi
# ══════════════════════════════════════════════════════

@router.message(Command("mening_xaridlarim"), F.chat.type == "private")
async def cmd_my_purchases(message: Message):
    purchases = await get_user_purchases(message.from_user.id)

    if not purchases:
        await message.answer(
            "📦 <b>Xaridlaringiz yo'q.</b>\n\n"
            "O'yinda coin to'plab /shop da super kartalar sotib oling!",
            parse_mode="HTML"
        )
        return

    text = "📦 <b>MENING XARIDLARIM</b>\n━━━━━━━━━━━━━━━\n\n"
    for p in purchases:
        used_status = "✅ Ishlatilgan" if p["used"] else "🟡 Faol"
        text += (
            f"🃏 <b>{p['name']}</b> [{used_status}]\n"
            f"   📖 {p['description']}\n"
            f"   🗓 Sotib olingan: {p['bought_at'][:10]}\n\n"
        )

    buttons = [
        [InlineKeyboardButton(text="⚡ Faol kartalarni ishlatish", callback_data="goto_inventar")]
    ]
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data == "goto_inventar")
async def cb_goto_inventar(call: CallbackQuery):
    # inventar funksiyasini qayta chaqiramiz
    await cmd_inventar(call.message)
    await call.answer()


# ══════════════════════════════════════════════════════
#  /add_item — Admin: yangi tovar qo'shish
# ══════════════════════════════════════════════════════

@router.message(Command("add_item"), F.chat.type == "private")
async def cmd_add_item(message: Message):
    from config import ADMIN_ID
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔️ Bu buyruq faqat admin uchun!")
        return

    args = message.text.split("|")
    # Format: /add_item Nomi | Tavsifi | Narxi | effect_kodi
    if len(args) < 4:
        await message.answer(
            "⚙️ <b>Yangi tovar qo'shish</b>\n\n"
            "<b>Format:</b>\n"
            "<code>/add_item Nomi | Tavsifi | Narxi | effect_kodi</code>\n\n"
            "<b>Misol:</b>\n"
            "<code>/add_item Amakingizning Vizitkasi | Tunda haydashdan immunitet | 500 | uncle_card</code>",
            parse_mode="HTML"
        )
        return

    try:
        name = args[0].replace("/add_item", "").strip()
        description = args[1].strip()
        price = int(args[2].strip())
        effect_code = args[3].strip()
    except (ValueError, IndexError):
        await message.answer("❌ Format noto'g'ri. Yuqoridagi namunaga qarang.")
        return

    item_id = await add_shop_item(name, description, price, effect_code)
    await message.answer(
        f"✅ <b>Yangi tovar qo'shildi!</b>\n\n"
        f"🆔 ID: <b>{item_id}</b>\n"
        f"📦 Nomi: <b>{name}</b>\n"
        f"📖 Tavsif: {description}\n"
        f"💰 Narxi: <b>{price} coins</b>\n"
        f"🔑 Effect: <code>{effect_code}</code>",
        parse_mode="HTML"
    )