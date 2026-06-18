# handlers/private_chat.py

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command

from config import ADMIN_ID
from database.db_main import (
    register_user, get_user, get_coins,
    get_all_shop_items, get_shop_item, buy_item, get_user_purchases,
    add_shop_item, save_ariza, get_active_game,
    get_player, get_game_by_id
)

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

    await message.answer(
        f"👨‍⚖️ <b>SUD TIZIMI</b> botiga xush kelibsiz!\n\n"
        f"💰 Balansingiz: <b>{coins} Court Coins</b>\n\n"
        f"📋 <b>Mavjud buyruqlar:</b>\n"
        f"  🛒 /shop — Do'kon (super kartalar)\n"
        f"  📦 /mening_xaridlarim — Xaridlarim\n"
        f"  📝 /ariza [sabab] — Sudyaga ariza yuborish\n"
        f"  💰 /balans — Coin balansim\n\n"
        f"{'⚙️ /add_item — Yangi tovar qo'shish (Admin)' if message.from_user.id == ADMIN_ID else ''}",
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────
#  /balans — Coin balansi
# ─────────────────────────────────────────────────────

@router.message(Command("balans"), F.chat.type == "private")
async def cmd_balans(message: Message):
    coins = await get_coins(message.from_user.id)
    await message.answer(
        f"💰 <b>Sizning balansingiz:</b>\n\n"
        f"🏅 <b>{coins} Court Coins</b>\n\n"
        f"O'yinda g'alaba qozonib coin to'plang va /shop da sarflang!",
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────
#  /shop — Do'kon
# ─────────────────────────────────────────────────────

@router.message(Command("shop"), F.chat.type == "private")
async def cmd_shop(message: Message):
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

    text = f"🛒 <b>SUPER KARTALAR DO'KONI</b>\n\n💰 Balansingiz: <b>{coins} coins</b>\n\n"
    buttons = []

    for item in items:
        affordable = "✅" if coins >= item["price"] else "❌"
        text += (
            f"{affordable} <b>{item['name']}</b>\n"
            f"   💬 {item['description']}\n"
            f"   💰 Narxi: {item['price']} coins\n\n"
        )
        buttons.append([
            InlineKeyboardButton(
                text=f"🛍 {item['name']} — {item['price']} coins",
                callback_data=f"buy_{item['item_id']}"
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("buy_"), F.message.chat.type == "private")
async def cb_buy_item(call: CallbackQuery):
    item_id = int(call.data.split("_")[1])
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

    # Tasdiqlash tugmasi
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, sotib olaman!", callback_data=f"confirm_buy_{item_id}"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_buy"),
        ]
    ])
    await call.message.answer(
        f"🛍 <b>Xaridni tasdiqlang</b>\n\n"
        f"📦 <b>{item['name']}</b>\n"
        f"💬 {item['description']}\n"
        f"💰 Narxi: <b>{item['price']} coins</b>\n\n"
        f"Balansingizdan {item['price']} coins hisobdan chiqariladi.",
        parse_mode="HTML",
        reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data.startswith("confirm_buy_"), F.message.chat.type == "private")
async def cb_confirm_buy(call: CallbackQuery):
    item_id = int(call.data.split("_")[2])
    success = await buy_item(call.from_user.id, item_id)

    if success:
        item = await get_shop_item(item_id)
        coins = await get_coins(call.from_user.id)
        await call.message.edit_text(
            f"🎉 <b>Xarid muvaffaqiyatli!</b>\n\n"
            f"📦 <b>{item['name']}</b> sizniki bo'ldi!\n"
            f"💬 <i>{item['description']}</i>\n\n"
            f"💰 Qolgan balans: <b>{coins} coins</b>\n\n"
            f"Xaridlaringizni /mening_xaridlarim orqali ko'ring.",
            parse_mode="HTML"
        )
    else:
        await call.message.edit_text(
            "❌ Xarid amalga oshmadi. Coinlar yetarli emas yoki xato yuz berdi.",
            parse_mode="HTML"
        )
    await call.answer()


@router.callback_query(F.data == "cancel_buy", F.message.chat.type == "private")
async def cb_cancel_buy(call: CallbackQuery):
    await call.message.edit_text("❌ Xarid bekor qilindi.")
    await call.answer()


# ─────────────────────────────────────────────────────
#  /mening_xaridlarim — Xaridlar tarixi
# ─────────────────────────────────────────────────────

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

    text = "📦 <b>MENING XARIDLARIM</b>\n\n"
    for p in purchases:
        used_status = "✅ Ishlatilgan" if p["used"] else "🟡 Faol"
        text += (
            f"🃏 <b>{p['name']}</b> [{used_status}]\n"
            f"   💬 {p['description']}\n"
            f"   🗓 Sotib olingan: {p['bought_at'][:10]}\n\n"
        )

    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────────────
#  /ariza — Sudyaga ariza yuborish
# ─────────────────────────────────────────────────────

@router.message(Command("ariza"), F.chat.type == "private")
async def cmd_ariza(message: Message, bot: Bot):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "📝 <b>Ariza yozish:</b>\n\n"
            "Foydalanish: <code>/ariza [sabab]</code>\n\n"
            "Misol: <code>/ariza Internetim yo'q, yozma gapira olaman</code>",
            parse_mode="HTML"
        )
        return

    ariza_text = args[1].strip()

    # Faol o'yinni topish (user qaysi o'yinda ekanini bilmaymiz,
    # shuning uchun user_id orqali player jadvalini qidiramiz)
    # Bu yerda foydalanuvchi o'yin chat_id sini ham yuborishi mumkin.
    # Oddiyroq yechim: eng oxirgi faol o'yinda qidirish.
    await message.answer(
        "⏳ Arizangiz tekshirilmoqda...\n"
        "Sudyaga yuborildi, javobni kuting."
    )

    # Sudyaga yuborish
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Arizani Tasdiqlash",
            callback_data=f"admin_ariza_{message.from_user.id}"
        )],
        [InlineKeyboardButton(
            text="❌ Rad etish",
            callback_data=f"reject_ariza_{message.from_user.id}"
        )]
    ])

    try:
        await bot.send_message(
            ADMIN_ID,
            f"📨 <b>YANGI ARIZA!</b>\n\n"
            f"👤 <b>Kimdan:</b> {message.from_user.full_name} "
            f"(@{message.from_user.username or 'username yo\'q'})\n"
            f"🆔 ID: <code>{message.from_user.id}</code>\n\n"
            f"📝 <b>Ariza matni:</b>\n{ariza_text}",
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception:
        await message.answer("❌ Sudyaga ariza yuborishda xato. Keyinroq urinib ko'ring.")


@router.callback_query(F.data.startswith("admin_ariza_"))
async def cb_admin_approve_ariza(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ Faqat Sudya!", show_alert=True)
        return

    user_id = int(call.data.split("_")[2])

    try:
        await bot.send_message(
            user_id,
            "✅ <b>Arizangiz tasdiqlandi!</b>\n\n"
            "Jamoangiz navbati kelganda guruh chatiga YOZMA xabar yuborishingiz mumkin.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await call.message.edit_text(
        call.message.text + "\n\n✅ <b>TASDIQLANDI</b>",
        parse_mode="HTML"
    )
    await call.answer("✅ Ariza tasdiqlandi!")


@router.callback_query(F.data.startswith("reject_ariza_"))
async def cb_admin_reject_ariza(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ Faqat Sudya!", show_alert=True)
        return

    user_id = int(call.data.split("_")[2])

    try:
        await bot.send_message(
            user_id,
            "❌ <b>Arizangiz rad etildi.</b>\n\n"
            "Sudya sizning ovozli chat orqali gapirishingizni talab qiladi.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await call.message.edit_text(
        call.message.text + "\n\n❌ <b>RAD ETILDI</b>",
        parse_mode="HTML"
    )
    await call.answer("❌ Ariza rad etildi.")


# ─────────────────────────────────────────────────────
#  /add_item — Admin: yangi tovar qo'shish
# ─────────────────────────────────────────────────────

@router.message(Command("add_item"), F.chat.type == "private")
async def cmd_add_item(message: Message):
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
            "<code>/add_item Amakingizning Vizitkasi | Tunda haydashdan immunitet | 500 | night_immunity</code>",
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
        f"💬 Tavsif: {description}\n"
        f"💰 Narxi: <b>{price} coins</b>\n"
        f"🔑 Effect: <code>{effect_code}</code>",
        parse_mode="HTML"
    )