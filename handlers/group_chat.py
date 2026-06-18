# handlers/group_chat.py

import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, ChatPermissions, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    VideoChatStarted
)
from aiogram.filters import Command

from config import ADMIN_ID
from database.db_main import (
    create_game, get_active_game, update_game_status,
    add_player, get_players, get_player, get_team_players, get_alive_players,
    set_current_turn, set_team_mute, set_player_mute,
    eliminate_player, increment_round, reward_winners,
    register_user, save_ariza, approve_ariza, get_pending_arizalar,
    get_game_by_id, set_voice_chat_verified
)

logger = logging.getLogger(__name__)
router = Router()

ROLES_WHITE = ["Advokat", "Guvoh (Oq)", "Fuqaro 1", "Fuqaro 2"]
ROLES_BLACK = ["Prokuror", "Guvoh (Qora)", "Jinoyatchi 1", "Jinoyatchi 2"]


# ══════════════════════════════════════════════════════
#  YORDAMCHI: CHAT MUZLATISH / OCHISH
# ══════════════════════════════════════════════════════

async def freeze_chat(bot: Bot, chat_id: int):
    await bot.set_chat_permissions(
        chat_id=chat_id,
        permissions=ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
        ),
    )

async def unfreeze_chat(bot: Bot, chat_id: int):
    await bot.set_chat_permissions(
        chat_id=chat_id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        ),
    )

async def allow_write_for_player(bot: Bot, chat_id: int, user_id: int):
    await bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=False,
            can_send_other_messages=False,
        ),
    )

async def mute_voice_team(bot: Bot, chat_id: int, players: list, muted: bool):
    for p in players:
        try:
            perms = ChatPermissions(can_send_messages=not muted)
            await bot.restrict_chat_member(chat_id=chat_id, user_id=p["user_id"], permissions=perms)
            await set_player_mute(p["game_id"], p["user_id"], muted)
        except Exception:
            pass


# ══════════════════════════════════════════════════════
#  YORDAMCHI: SUDYA KLAVIATURASI
# ══════════════════════════════════════════════════════

def _build_judge_kb(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎤 Oqlar Gapirsin",   callback_data=f"unmute_white_{game_id}"),
                InlineKeyboardButton(text="🎤 Qoralar Gapirsin", callback_data=f"unmute_black_{game_id}"),
            ],
            [InlineKeyboardButton(text="🔇 Hammani Jim Qil", callback_data=f"mute_all_{game_id}")],
            [InlineKeyboardButton(text="⚖️ O'yinni Yakunlash",  callback_data=f"end_game_{game_id}")],
        ]
    )


# ══════════════════════════════════════════════════════
#  /yangi_ish — Yangi jinoiy ish ochish
# ══════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════
#  /yangi_ish — Yangi jinoiy ish ochish (Mavzu bilan)
# ══════════════════════════════════════════════════════

@router.message(Command("yangi_ish"))
async def cmd_yangi_ish(message: Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔️ Bu buyruq faqat Bosh Sudya (admin) uchun!")
        return
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("⚠️ Bu buyruq faqat guruhda ishlaydi.")
        return

    existing = await get_active_game(message.chat.id)
    if existing:
        await message.reply(
            f"⚠️ Allaqachon faol o'yin mavjud (ID: {existing['game_id']})\n"
            "Avval /end_court buyrug'i bilan yakunlang."
        )
        return

    # Buyruqdan keyingi matnni (ish mavzusini) ajratib olamiz
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(
            "⚠️ <b>Iltimos, jinoiy ish mavzusini ham yozing!</b>\n\n"
            "<b>Format:</b>\n"
            "<code>/yangi_ish Ish nomi | Kulgili tafsilotlar</code>\n\n"
            "<b>Misol:</b>\n"
            "<code>/yangi_ish Somsa o'g'riligi | Ali likopchadagi oxirgi somsa va go'shtni so'ramasdan yeb qo'yganlikda ayblanmoqda.</code>",
            parse_mode="HTML"
        )
        return

    ish_mavzusi = args[1].strip()

    # O'yinni bazada yaratamiz
    game_id = await create_game(message.chat.id, message.from_user.id)
    await register_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚖️ Oq Jamoaga Qo'shilish",  callback_data=f"join_white_{game_id}")],
            [InlineKeyboardButton(text="🖤 Qora Jamoaga Qo'shilish", callback_data=f"join_black_{game_id}")],
        ]
    )
    
    await message.reply(
        f"🏛️ <b>SUD TIZIMI O'YINI BOSHLANDI!</b>\n\n"
        f"📋 <b>Ish raqami:</b> #{game_id}\n"
        f"👨‍⚖️ <b>Sudya:</b> {message.from_user.full_name}\n"
        f"🔍 <b>KUN TARTIBIDAGI JINOIY ISH:</b>\n"
        f"<blockquote>{ish_mavzusi}</blockquote>\n\n"
        f"Ishtirokchilar, quyidagi tugmalar orqali jamoangizni tanlang!\n\n"
        f"👥 <b>Ishtirokchilar ro'yxati:</b>\n<i>Hali hech kim qo'shilmadi...</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )


# ══════════════════════════════════════════════════════
#  JOIN CALLBACK — Jamoaga qo'shilish
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("join_white_") | F.data.startswith("join_black_"))
async def cb_join_team(call: CallbackQuery):
    parts   = call.data.split("_")
    team    = parts[1]
    game_id = int(parts[2])

    await register_user(call.from_user.id, call.from_user.username, call.from_user.full_name)

    if await get_player(game_id, call.from_user.id):
        await call.answer("Siz allaqachon o'yinga qo'shilgansiz!", show_alert=True)
        return

    players      = await get_players(game_id)
    team_players = [p for p in players if p["team"] == team]
    roles        = ROLES_WHITE if team == "white" else ROLES_BLACK
    team_name    = "⚖️ Oq Jamoa" if team == "white" else "🖤 Qora Jamoa"
    role         = roles[len(team_players) % len(roles)]

    await add_player(game_id, call.from_user.id, team, role)
    await call.answer(f"✅ {team_name} ga qo'shildingiz! Rolingiz: {role}", show_alert=True)

    all_players = await get_players(game_id)
    white_list  = [p for p in all_players if p["team"] == "white"]
    black_list  = [p for p in all_players if p["team"] == "black"]
    white_text  = "\n".join([f"  • User {p['user_id']}" for p in white_list]) or "  <i>Bo'sh</i>"
    black_text  = "\n".join([f"  • User {p['user_id']}" for p in black_list]) or "  <i>Bo'sh</i>"

    try:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚖️ Oq Jamoaga Qo'shilish",  callback_data=f"join_white_{game_id}")],
                [InlineKeyboardButton(text="🖤 Qora Jamoaga Qo'shilish", callback_data=f"join_black_{game_id}")],
            ]
        )
        await call.message.edit_text(
            f"🏛️ <b>SUD TIZIMI O'YINI</b> | Ish #{game_id}\n\n"
            f"⚖️ <b>Oq Jamoa:</b>\n{white_text}\n\n"
            f"🖤 <b>Qora Jamoa:</b>\n{black_text}\n\n"
            f"Admin /start_court buyrug'i bilan o'yinni boshlaydi.",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════
#  /start_court — O'yinni rasman boshlash
#  Video chat tekshiruvi o'chirildi — bevosita boshlanadi
# ══════════════════════════════════════════════════════

@router.message(Command("start_court"))
async def cmd_start_court(message: Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔️ Bu buyruq faqat Bosh Sudya uchun!")
        return

    game = await get_active_game(message.chat.id)
    if not game:
        await message.reply("❌ Faol o'yin topilmadi. Avval /yangi_ish bilan boshlang.")
        return
    if game["status"] == "active":
        await message.reply("⚠️ O'yin allaqachon boshlangan!")
        return

    players = await get_players(game["game_id"])
    if len(players) < 2:
        await message.reply("⚠️ O'yinga kamida 2 ta ishtirokchi kerak!")
        return

    await _launch_game(bot, message, game)


async def _launch_game(bot: Bot, message: Message, game: dict):
    """O'yinni to'liq ishga tushiradi."""
    await set_voice_chat_verified(game["game_id"], True)
    await update_game_status(game["game_id"], "active")
    await freeze_chat(bot, message.chat.id)
    await set_team_mute(game["game_id"], "white", True)
    await set_team_mute(game["game_id"], "black", True)

    white_players = await get_team_players(game["game_id"], "white")
    black_players = await get_team_players(game["game_id"], "black")
    await mute_voice_team(bot, message.chat.id, white_players, True)
    await mute_voice_team(bot, message.chat.id, black_players, True)

    kb = _build_judge_kb(game["game_id"])
    await message.reply(
        "⚖️ <b>SUD MAJLISI OCHILDI!</b>\n\n"
        "🎙️ Guruh chati muzlatildi.\n"
        "Faqat Sudya tugmalar orqali so'z beradi.\n\n"
        "👨‍⚖️ <b>Sudya boshqaruvi:</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )


# ══════════════════════════════════════════════════════
#  SUDYA TUGMALARI — Mikrofon boshqaruvi
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("unmute_white_"))
async def cb_unmute_white(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ Faqat Sudya boshqara oladi!", show_alert=True)
        return
    game_id = int(call.data.split("_")[2])
    game    = await get_game_by_id(game_id)

    black_players = await get_team_players(game_id, "black")
    white_players = await get_team_players(game_id, "white")
    await mute_voice_team(bot, game["chat_id"], black_players, True)
    await mute_voice_team(bot, game["chat_id"], white_players, False)
    await set_current_turn(game_id, "white")
    await call.answer("✅ Oq jamoa mikrofoni ochildi!")
    await call.message.reply(
        "🎤 <b>So'z OQ JAMOAGA berildi!</b>\nQora jamoa mikrofonlari o'chirildi.",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("unmute_black_"))
async def cb_unmute_black(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ Faqat Sudya boshqara oladi!", show_alert=True)
        return
    game_id = int(call.data.split("_")[2])
    game    = await get_game_by_id(game_id)

    white_players = await get_team_players(game_id, "white")
    black_players = await get_team_players(game_id, "black")
    await mute_voice_team(bot, game["chat_id"], white_players, True)
    await mute_voice_team(bot, game["chat_id"], black_players, False)
    await set_current_turn(game_id, "black")
    await call.answer("✅ Qora jamoa mikrofoni ochildi!")
    await call.message.reply(
        "🎤 <b>So'z QORA JAMOAGA berildi!</b>\nOq jamoa mikrofonlari o'chirildi.",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("mute_all_"))
async def cb_mute_all(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ Faqat Sudya boshqara oladi!", show_alert=True)
        return
    game_id     = int(call.data.split("_")[2])
    game        = await get_game_by_id(game_id)
    all_players = await get_alive_players(game_id)
    await mute_voice_team(bot, game["chat_id"], all_players, True)
    await call.answer("🔇 Barcha mikrofonlar o'chirildi!")
    await call.message.reply("🔇 <b>Barcha ishtirokchilar jim qilindi.</b>", parse_mode="HTML")


# ══════════════════════════════════════════════════════
#  !dalil — Dalilni PIN qilish
# ══════════════════════════════════════════════════════

@router.message(F.text.startswith("!dalil"))
async def cmd_dalil(message: Message, bot: Bot):
    game = await get_active_game(message.chat.id)
    if not game or game["status"] != "active":
        return

    player = await get_player(game["game_id"], message.from_user.id)
    if not player or not player["is_alive"]:
        await message.reply("⛔️ Siz o'yinda yo'qsiz yoki chiqarib yuborilgansiz!")
        return
    if player["team"] != game["current_turn"]:
        await message.reply("⏳ Hozir sizning jamoangizning navbati emas!")
        return

    dalil_text = message.text[6:].strip()
    caption = (
        f"📌 <b>DALIL TAQDIM ETILDI</b>\n\n"
        f"👤 <b>Kimdan:</b> {message.from_user.full_name}\n"
        f"🏷️ <b>Rol:</b> {player['role']}\n"
        f"💬 <b>Dalil:</b> {dalil_text or '(Rasm/fayl yuborildi)'}"
    )
    try:
        await bot.pin_chat_message(message.chat.id, message.message_id)
        await message.reply(caption, parse_mode="HTML")
    except Exception as e:
        await message.reply(f"⚠️ Dalilni pin qilishda xato: {e}")


# ══════════════════════════════════════════════════════
#  ARIZA TASDIQLASH
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("approve_ariza_"))
async def cb_approve_ariza(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ Faqat Sudya tasdiqlaydi!", show_alert=True)
        return
    parts   = call.data.split("_")
    game_id = int(parts[2])
    user_id = int(parts[3])
    game    = await get_game_by_id(game_id)
    await approve_ariza(game_id, user_id)
    await allow_write_for_player(bot, game["chat_id"], user_id)
    await call.answer("✅ Ariza tasdiqlandi, o'yinchiga yozma ruxsat berildi!")
    await call.message.edit_text(
        call.message.text + "\n\n✅ <b>TASDIQLANDI</b>",
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════════
#  O'YINNI YAKUNLASH
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("end_game_"))
async def cb_end_game(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ Faqat Sudya yakunlay oladi!", show_alert=True)
        return
    game_id = int(call.data.split("_")[2])
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚖️ OQ JAMOA G'ALABA",  callback_data=f"winner_white_{game_id}"),
                InlineKeyboardButton(text="🖤 QORA JAMOA G'ALABA", callback_data=f"winner_black_{game_id}"),
            ]
        ]
    )
    await call.message.reply(
        "⚖️ <b>O'yin yakunlanmoqda!</b>\nQaysi jamoa g'alaba qozondi?",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data.startswith("winner_"))
async def cb_winner(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⛔️ Faqat Sudya!", show_alert=True)
        return
    parts   = call.data.split("_")
    team    = parts[1]
    game_id = int(parts[2])
    game    = await get_game_by_id(game_id)

    winner_ids = await reward_winners(game_id, team)
    await update_game_status(game_id, "finished")
    await unfreeze_chat(bot, game["chat_id"])

    team_emoji = "⚖️ OQ" if team == "white" else "🖤 QORA"
    mentions   = " | ".join([f"<a href='tg://user?id={uid}'>🏆</a>" for uid in winner_ids])

    await call.message.reply(
        f"🎉 <b>SUD MAJLISI YAKUNLANDI!</b>\n\n"
        f"🏆 <b>G'OLIB: {team_emoji} JAMOA!</b>\n\n"
        f"{mentions}\n\n"
        f"💰 Har bir g'olibga <b>+200 Court Coins</b> berildi!\n"
        f"🛒 /shop orqali sovg'alar sotib oling!",
        parse_mode="HTML",
    )
    await call.answer("✅ O'yin yakunlandi!")


# ══════════════════════════════════════════════════════
#  /end_court — Majburiy to'xtatish
# ══════════════════════════════════════════════════════

@router.message(Command("end_court"))
async def cmd_end_court(message: Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔️ Faqat admin!")
        return
    game = await get_active_game(message.chat.id)
    if not game:
        await message.reply("❌ Faol o'yin yo'q.")
        return

    await update_game_status(game["game_id"], "finished")
    await unfreeze_chat(bot, message.chat.id)
    await message.reply("🏛️ O'yin majburiy ravishda to'xtatildi. Guruh chati ochildi.")
