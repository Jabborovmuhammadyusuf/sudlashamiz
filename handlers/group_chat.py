# handlers/group_chat.py
# Sud Tizimi — To'liq yangilangan guruh handler moduli
#
# Yangiliklar:
#  - Erkin Sudya (istalgan foydalanuvchi /yangi_ish berib boshlaydi)
#  - Bot permissions tekshiruvi
#  - 5 raundli debat tizimi
#  - !dalil + PIN + 120 soniya taymer
#  - Sudyaga 1-5 ball berish paneli (anti-cheat)
#  - Durang → Yakuniy Verdikt paneli
#  - Rollar tizimi + tungi funksiyalar (lichkada)
#  - Impechment (/arz_sudya) + AFK taymer (3 daqiqa)
#  - Real Ayblanuvchi + 30 daqiqalik Mute jazosi
#  - Bail Card (kafillik shartnomasi) himoyasi
#  - Matnli rejim avtomatizatsiyasi
#  - Karma tizimi (o'yin oxirida sudyani baholash)

import asyncio
import logging
import random
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, ChatPermissions, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command

from database.db_main import (
    create_game, get_active_game, update_game_status, update_game_phase,
    add_player, get_players, get_player, get_team_players, get_alive_players,
    set_current_turn, set_team_mute, set_player_mute,
    eliminate_player, reward_winners, penalize_losers,
    register_user, save_ariza, approve_ariza, get_pending_arizalar,
    get_game_by_id, set_voice_chat_verified, set_text_mode,
    increment_voice_warn, update_judge_action_time, transfer_judge,
    mark_dalil_used, add_score, save_round_score, get_round_scores,
    increment_round, set_accused, set_night_blocked, set_night_protected,
    set_player_immunity, set_player_bail, reset_night_statuses,
    save_night_action, get_night_actions, mark_night_action_processed,
    get_player_night_action, cast_impeachment_vote,
    check_ariza_cooldown, update_ariza_cooldown,
    cast_karma_vote, get_karma_summary,
    add_coins, add_rating, get_user_purchases, mark_item_used
)

logger = logging.getLogger(__name__)
router = Router()

# ══════════════════════════════════════════════════════
#  ROLLAR TIZIMI
#  Har bir rol: team, tungi funksiya kodi
# ══════════════════════════════════════════════════════

ROLES = {
    # Oq jamoa rollari
    "Xususiy Detektiv": {
        "team": "white",
        "night_action": "detective",
        "description": "Tunda biror ishtirokchini tekshiradi — uning jamoasini biladi.",
    },
    "Sud-tibbiyot Eksperti": {
        "team": "white",
        "night_action": "forensic",
        "description": "Chiqarilgan shaxsning asl rolini bilib oladi.",
    },
    "Advokat": {
        "team": "white",
        "night_action": None,
        "description": "Oqlar jamoasining asosiy so'z egasi.",
    },
    "Fuqaro (Oq)": {
        "team": "white",
        "night_action": None,
        "description": "Oddiy fuqaro — himoyachilar safida.",
    },
    # Qora jamoa rollari
    "Soxta Guvoh": {
        "team": "black",
        "night_action": "fake_witness",
        "description": "Tunda biror o'yinchi ustidan feyk ko'rsatma yozadi.",
    },
    "Arxiv Xodimi": {
        "team": "black",
        "night_action": "archive",
        "description": "Sherigini bir kecha detektiv tekshiruvlaridan himoya qiladi.",
    },
    "Prokuror": {
        "team": "black",
        "night_action": None,
        "description": "Qoralar jamoasining asosiy ayblovchisi.",
    },
    "Jinoyatchi": {
        "team": "black",
        "night_action": None,
        "description": "Qoralar safida.",
    },
    # Neytral rol (alohida assign)
    "Sud Pristavi": {
        "team": "neutral",
        "night_action": "bailiff",
        "description": "Tunda biror o'yinchini bir raundga 'sud zalidan chiqaradi'.",
    },
}

# Jamoaga tayinlash uchun tartib
ROLES_WHITE_ORDER = [
    "Advokat", "Xususiy Detektiv", "Fuqaro (Oq)", "Sud-tibbiyot Eksperti",
    "Fuqaro (Oq)", "Fuqaro (Oq)"
]
ROLES_BLACK_ORDER = [
    "Prokuror", "Soxta Guvoh", "Jinoyatchi", "Arxiv Xodimi",
    "Jinoyatchi", "Jinoyatchi"
]

MAX_ROUNDS = 5
AFK_SECONDS = 180        # 3 daqiqa
DALIL_TIMER_SECONDS = 120  # 2 daqiqa
MUTE_DURATION_MINUTES = 30


# ══════════════════════════════════════════════════════
#  YORDAMCHI: CHAT MUZLATISH / OCHISH
# ══════════════════════════════════════════════════════

async def freeze_chat(bot: Bot, chat_id: int):
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
        )
    except Exception as e:
        logger.warning(f"freeze_chat xato: {e}")


async def unfreeze_chat(bot: Bot, chat_id: int):
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
    except Exception as e:
        logger.warning(f"unfreeze_chat xato: {e}")


async def allow_write_for_player(bot: Bot, chat_id: int, user_id: int):
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=False,
                can_send_other_messages=False,
            ),
        )
    except Exception as e:
        logger.warning(f"allow_write_for_player xato: {e}")


async def mute_user(bot: Bot, chat_id: int, user_id: int, muted: bool):
    try:
        perms = ChatPermissions(can_send_messages=not muted)
        await bot.restrict_chat_member(
            chat_id=chat_id, user_id=user_id, permissions=perms
        )
        await set_player_mute(0, user_id, muted)  # game_id=0 chunki biz chat_id ishlatyapmiz
    except Exception as e:
        logger.warning(f"mute_user xato (uid={user_id}): {e}")


async def mute_team(bot: Bot, chat_id: int, game_id: int,
                    team: str, muted: bool):
    players = await get_team_players(game_id, team)
    for p in players:
        try:
            perms = ChatPermissions(can_send_messages=not muted)
            await bot.restrict_chat_member(
                chat_id=chat_id, user_id=p["user_id"], permissions=perms
            )
            await set_player_mute(game_id, p["user_id"], muted)
        except Exception as e:
            logger.warning(f"mute_team xato (uid={p['user_id']}): {e}")


async def mute_all_players(bot: Bot, chat_id: int, game_id: int):
    players = await get_alive_players(game_id)
    for p in players:
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id, user_id=p["user_id"],
                permissions=ChatPermissions(can_send_messages=False)
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════
#  YORDAMCHI: BOT PERMISSIONS TEKSHIRUVI
# ══════════════════════════════════════════════════════

async def check_bot_permissions(bot: Bot, chat_id: int) -> tuple[bool, str]:
    """
    Botning delete, restrict, pin ruxsatlarini tekshiradi.
    Qaytaradi: (ok: bool, error_text: str)
    """
    try:
        bot_member = await bot.get_chat_member(chat_id, (await bot.get_me()).id)
        missing = []

        perms = getattr(bot_member, "can_delete_messages", None)
        if not perms:
            missing.append("❌ Xabarlarni o'chirish (<b>Delete messages</b>)")

        perms = getattr(bot_member, "can_restrict_members", None)
        if not perms:
            missing.append("❌ Foydalanuvchilarni cheklash (<b>Restrict members</b>)")

        perms = getattr(bot_member, "can_pin_messages", None)
        if not perms:
            missing.append("❌ Xabarlarni qatirish (<b>Pin messages</b>)")

        if missing:
            error = (
                "⚠️ <b>Bot kerakli ruxsatlarga ega emas!</b>\n\n"
                "O'yinni boshlash uchun botga quyidagi ruxsatlar berilishi SHART:\n\n"
                + "\n".join(missing)
                + "\n\n<i>Guruh sozlamalariga kiring → Adminlar → Botni toping → Ruxsatlarni yoqing.</i>"
            )
            return False, error

        return True, ""
    except Exception as e:
        return False, f"⚠️ Ruxsatlarni tekshirishda xato: {e}"


# ══════════════════════════════════════════════════════
#  YORDAMCHI: SUDYA KLAVIATURASI
# ══════════════════════════════════════════════════════

def _judge_main_kb(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚖️ Oqlarga so'z",
                    callback_data=f"unmute_white_{game_id}"
                ),
                InlineKeyboardButton(
                    text="🖤 Qoralarga so'z",
                    callback_data=f"unmute_black_{game_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔇 Hammani jim qil",
                    callback_data=f"mute_all_{game_id}"
                ),
                InlineKeyboardButton(
                    text="🌙 Tun fazasini boshlash",
                    callback_data=f"start_night_{game_id}"
                ),
            ],
            [InlineKeyboardButton(
                text="⚖️ O'yinni yakunlash",
                callback_data=f"end_game_{game_id}"
            )],
        ]
    )


def _scoring_kb(game_id: int) -> InlineKeyboardMarkup:
    """Ball berish paneli — har raund oxiri."""
    rows = []
    for team, label in [("white", "⚖️ Oqlarga ball"), ("black", "🖤 Qoralarga ball")]:
        row = [
            InlineKeyboardButton(
                text=f"{label} ({i})",
                callback_data=f"score_{team}_{i}_{game_id}"
            )
            for i in range(1, 6)
        ]
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _verdict_kb(game_id: int) -> InlineKeyboardMarkup:
    """Durang bo'lganda Yakuniy Verdikt paneli."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Oqlash (Himoyachilar g'alaba)",
                    callback_data=f"verdict_white_{game_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⛔ Ayblash (Ayblovchilar g'alaba)",
                    callback_data=f"verdict_black_{game_id}"
                ),
            ],
        ]
    )


def _karma_kb(game_id: int, judge_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👍 Sudya yaxshi edi",
                    callback_data=f"karma_plus_{game_id}_{judge_id}"
                ),
                InlineKeyboardButton(
                    text="👎 Sudya yomon edi",
                    callback_data=f"karma_minus_{game_id}_{judge_id}"
                ),
            ]
        ]
    )


# ══════════════════════════════════════════════════════
#  /yangi_ish — Yangi jinoiy ish ochish (ERKIN SUDYA)
# ══════════════════════════════════════════════════════

@router.message(Command("yangi_ish"))
async def cmd_yangi_ish(message: Message, bot: Bot):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("⚠️ Bu buyruq faqat guruhda ishlaydi.")
        return

    # 1. Bot permissions tekshiruvi
    ok, err = await check_bot_permissions(bot, message.chat.id)
    if not ok:
        await message.reply(err, parse_mode="HTML")
        return

    # 2. Allaqachon aktiv o'yin bormi?
    existing = await get_active_game(message.chat.id)
    if existing:
        await message.reply(
            f"⚠️ Allaqachon faol o'yin mavjud (ID: #{existing['game_id']})\n"
            "Avval /end_court bilan yakunlang.",
            parse_mode="HTML"
        )
        return

    # 3. Ish mavzusi
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(
            "⚠️ <b>Iltimos, jinoiy ish mavzusini ham yozing!</b>\n\n"
            "<b>Format:</b>\n"
            "<code>/yangi_ish Ish nomi | Kulgili tafsilotlar</code>\n\n"
            "<b>Misol:</b>\n"
            "<code>/yangi_ish Somsa o'g'riligi | Ali likopchadagi oxirgi somsani "
            "so'ramasdan yeb qo'yganlikda ayblanmoqda.</code>",
            parse_mode="HTML"
        )
        return

    ish_mavzusi = args[1].strip()

    # 4. O'yinni yaratish — O'yinni boshlagan kishi Sudya bo'ladi
    await register_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )
    game_id = await create_game(
        message.chat.id,
        message.from_user.id,
        ish_mavzusi
    )
    await update_game_phase(game_id, "registration")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="⚖️ Oq Jamoaga Qo'shilish",
                callback_data=f"join_white_{game_id}"
            )],
            [InlineKeyboardButton(
                text="🖤 Qora Jamoaga Qo'shilish",
                callback_data=f"join_black_{game_id}"
            )],
            [InlineKeyboardButton(
                text="▶️ O'yinni Boshlash",
                callback_data=f"start_game_{game_id}"
            )],
        ]
    )

    await message.reply(
        f"🏛️ <b>SUD TIZIMI O'YINI BOSHLANDI!</b>\n\n"
        f"📋 <b>Ish raqami:</b> #{game_id}\n"
        f"👨‍⚖️ <b>Sudya:</b> {message.from_user.full_name} <i>(Neytral)</i>\n\n"
        f"🔍 <b>KUN TARTIBIDAGI JINOIY ISH:</b>\n"
        f"<blockquote>{ish_mavzusi}</blockquote>\n\n"
        f"Ishtirokchilar jamoalarini tanlashsin.\n"
        f"<i>Sudya o'yinchi sifatida qatnashmaydi.</i>\n\n"
        f"👥 <b>Ishtirokchilar:</b> <i>hali hech kim...</i>",
        parse_mode="HTML",
        reply_markup=kb,
    )


# ══════════════════════════════════════════════════════
#  JOIN — Jamoaga qo'shilish
# ══════════════════════════════════════════════════════

@router.callback_query(
    F.data.startswith("join_white_") | F.data.startswith("join_black_")
)
async def cb_join_team(call: CallbackQuery):
    parts = call.data.split("_")
    team = parts[1]        # "white" | "black"
    game_id = int(parts[2])

    game = await get_game_by_id(game_id)
    if not game or game["phase"] != "registration":
        await call.answer("⚠️ Ro'yxatga olish bosqichi tugagan!", show_alert=True)
        return

    # Sudya o'yinga kira olmaydi
    if call.from_user.id == game["judge_id"]:
        await call.answer(
            "⛔ Sudya o'yinga ishtirokchi sifatida kira olmaydi!",
            show_alert=True
        )
        return

    await register_user(
        call.from_user.id,
        call.from_user.username,
        call.from_user.full_name
    )

    if await get_player(game_id, call.from_user.id):
        await call.answer("Siz allaqachon qo'shilgansiz!", show_alert=True)
        return

    # Rol tayinlash
    players = await get_players(game_id)
    team_players = [p for p in players if p["team"] == team]
    roles_order = ROLES_WHITE_ORDER if team == "white" else ROLES_BLACK_ORDER
    role = roles_order[len(team_players) % len(roles_order)]
    team_label = "⚖️ Oq Jamoa" if team == "white" else "🖤 Qora Jamoa"

    await add_player(game_id, call.from_user.id, team, role)
    await call.answer(
        f"✅ {team_label} ga qo'shildingiz!\nRolingiz: {role}\n"
        f"(Rol detallari lichkangizda)",
        show_alert=True
    )

    # Lichkaga rol xabari
    try:
        role_info = ROLES.get(role, {})
        await call.bot.send_message(
            call.from_user.id,
            f"🎭 <b>O'YIN #{game_id} — SIZNING ROLINGIZ</b>\n\n"
            f"{'⚖️' if team == 'white' else '🖤'} Jamoa: <b>{team_label}</b>\n"
            f"🎭 Rol: <b>{role}</b>\n\n"
            f"📖 {role_info.get('description', '')}\n\n"
            f"<i>Rolni hech kimga aytmang — o'yin yakunigacha sir!</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass  # foydalanuvchi botni bloklamagan bo'lishi kerak

    # Xabarni yangilash
    all_players = await get_players(game_id)
    white_list = [p for p in all_players if p["team"] == "white"]
    black_list = [p for p in all_players if p["team"] == "black"]

    white_text = "\n".join([
        f" • <a href='tg://user?id={p['user_id']}'>"
        f"O'yinchi {i+1}</a>"
        for i, p in enumerate(white_list)
    ]) or "  <i>Bo'sh</i>"
    black_text = "\n".join([
        f" • <a href='tg://user?id={p['user_id']}'>"
        f"O'yinchi {i+1}</a>"
        for i, p in enumerate(black_list)
    ]) or "  <i>Bo'sh</i>"

    try:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="⚖️ Oq Jamoaga Qo'shilish",
                    callback_data=f"join_white_{game_id}"
                )],
                [InlineKeyboardButton(
                    text="🖤 Qora Jamoaga Qo'shilish",
                    callback_data=f"join_black_{game_id}"
                )],
                [InlineKeyboardButton(
                    text="▶️ O'yinni Boshlash",
                    callback_data=f"start_game_{game_id}"
                )],
            ]
        )
        game = await get_game_by_id(game_id)
        await call.message.edit_text(
            f"🏛️ <b>SUD TIZIMI</b> | Ish #{game_id}\n\n"
            f"🔍 <blockquote>{game['ish_mavzusi']}</blockquote>\n\n"
            f"⚖️ <b>Oq Jamoa ({len(white_list)}):</b>\n{white_text}\n\n"
            f"🖤 <b>Qora Jamoa ({len(black_list)}):</b>\n{black_text}\n\n"
            f"Sudya ▶️ tugmasini bosib o'yinni boshlaydi.",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════
#  O'YINNI BOSHLASH (Sudya tugmasi)
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("start_game_"))
async def cb_start_game(call: CallbackQuery, bot: Bot):
    game_id = int(call.data.split("_")[2])
    game = await get_game_by_id(game_id)

    if not game:
        await call.answer("❌ O'yin topilmadi!", show_alert=True)
        return
    if call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya boshlaydi!", show_alert=True)
        return
    if game["status"] == "active":
        await call.answer("⚠️ O'yin allaqachon boshlangan!", show_alert=True)
        return

    players = await get_players(game_id)
    if len(players) < 2:
        await call.answer("⚠️ Kamida 2 ishtirokchi kerak!", show_alert=True)
        return

    # Video chat tekshiruvi
    await _check_voice_and_launch(bot, call.message, game, call.from_user.id)
    await call.answer()


async def _check_voice_and_launch(
    bot: Bot, message: Message, game: dict, judge_id: int
):
    """Video chat bormi? Yo'q bo'lsa 3 urinish, keyin matnli rejim."""
    try:
        chat = await bot.get_chat(game["chat_id"])
        has_voice = getattr(chat, "active_usernames", None) is not None
        # Telegram API to'g'ridan-to'g'ri video chat statusini bermaydi,
        # shuning uchun voice_warn_count orqali manual nazorat qilamiz.
        # Agar admin allaqachon 3 marta bosgan bo'lsa — matnli rejimga o'tamiz.
    except Exception:
        pass

    warn_count = game.get("voice_warn_count", 0)

    if warn_count < 3:
        # Ogohlantirish
        new_warn = await increment_voice_warn(game["game_id"])
        if new_warn < 3:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🎙️ Ovozli chat ochildi, boshlash!",
                        callback_data=f"start_game_{game['game_id']}"
                    )],
                    [InlineKeyboardButton(
                        text="📝 Matnli rejimda boshlash",
                        callback_data=f"force_text_{game['game_id']}"
                    )],
                ]
            )
            await message.reply(
                f"🎙️ <b>OGOHLANTIRISH {new_warn}/3</b>\n\n"
                f"O'yin boshlashdan avval Telegram <b>Ovozli chat</b>ni oching!\n\n"
                f"Agar ovozli chat ochilmasa, {3 - new_warn} ta urinishdan so'ng "
                f"o'yin <b>matnli rejimda</b> boshlanadi.",
                parse_mode="HTML",
                reply_markup=kb
            )
            return
        else:
            # 3-urinish — matnli rejimga o'tish
            await set_text_mode(game["game_id"], True)
            await message.reply(
                "📝 <b>Matnli rejim yoqildi!</b>\n\n"
                "Ovozli chat aniqlanmadi. O'yin matnli formatda davom etadi.\n"
                "Guruh chati to'liq muzlatiladi, faqat navbati kelgan jamoa yoza oladi.",
                parse_mode="HTML"
            )

    # O'yinni ishga tushirish
    await _launch_game(bot, message, game)


@router.callback_query(F.data.startswith("force_text_"))
async def cb_force_text(call: CallbackQuery, bot: Bot):
    game_id = int(call.data.split("_")[2])
    game = await get_game_by_id(game_id)
    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya!", show_alert=True)
        return
    await set_text_mode(game_id, True)
    await set_voice_chat_verified(game_id, True)
    await call.answer("✅ Matnli rejim yoqildi!")
    await _launch_game(bot, call.message, game)


async def _launch_game(bot: Bot, message: Message, game: dict):
    """O'yinni to'liq ishga tushiradi — 1-raundni boshlaydi."""
    game_id = game["game_id"]

    await set_voice_chat_verified(game_id, True)
    await update_game_status(game_id, "active")
    await update_game_phase(game_id, "day")
    await update_judge_action_time(game_id)

    # Guruhni muzlatish
    await freeze_chat(bot, game["chat_id"])
    await mute_all_players(bot, game["chat_id"], game_id)

    # Ayblanuvchini random tayinlash
    players = await get_alive_players(game_id)
    if players:
        accused = random.choice(players)
        await set_accused(game_id, accused["user_id"])
        # Ayblanuvchiga lichkada xabar
        try:
            await bot.send_message(
                accused["user_id"],
                f"⚠️ <b>DIQQAT!</b>\n\n"
                f"Siz o'yin #{game_id} da <b>REAL AYBLANUVCHI</b> sifatida tanlandingiz!\n\n"
                f"Bu degani: agar Qoralar jamoasi g'alaba qozonsa, "
                f"guruhda <b>{MUTE_DURATION_MINUTES} daqiqa mute</b> qilinasiz.\n\n"
                f"<i>Bu ma'lumot maxfiy — hech kimga aytmang!</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    # 1-raundni boshlash
    game_fresh = await get_game_by_id(game_id)
    await _announce_round(bot, message, game_fresh)

    # AFK taymerni fonda ishga tushirish
    asyncio.create_task(_afk_watcher(bot, game_id, game["chat_id"]))


# ══════════════════════════════════════════════════════
#  RAUND E'LONI
# ══════════════════════════════════════════════════════

# Har raund uchun qisqa tezislar
ROUND_THESES = [
    "Voqea joyidan topilgan oq Damas bamperi",
    "Dalil: Likopchadagi barmoq izi",
    "Guvoh: Kimdir eshik orqali kirib-chiqishini ko'rgan",
    "CCTV lavhasi: Shanba kuni soat 14:30 da shubhali harakatlar",
    "Sud-tibbiyot xulosasi: Maxsus iz qoldirilgan",
    "Bank hisobi: Bir kunda g'ayrioddiy to'lov",
    "Telefon yozishmasi: Kodli xabar topildi",
    "Yashirin guvoh: Biri hammadan oldin ketgan",
]


async def _announce_round(bot: Bot, message: Message, game: dict):
    game_id = game["game_id"]
    round_num = game["round_number"]
    thesis = ROUND_THESES[(round_num - 1) % len(ROUND_THESES)]

    judge = await bot.get_chat_member(game["chat_id"], game["judge_id"])
    judge_name = getattr(judge.user, "full_name", "Sudya")

    kb = _judge_main_kb(game_id)

    msg = await message.reply(
        f"⚖️ <b>RAUND {round_num}/{MAX_ROUNDS} BOSHLANDI!</b>\n\n"
        f"📋 <b>Raund tezisi:</b>\n"
        f"<blockquote>{thesis}</blockquote>\n\n"
        f"📌 <b>Qoidalar:</b>\n"
        f"• Har jamoa faqat <b>1 ta dalil</b> keltirishi mumkin\n"
        f"• Format: <code>!dalil [matn]</code>\n"
        f"• Dalil berganingizda 120 soniya taymeri boshlanadi\n\n"
        f"👨‍⚖️ Sudya: <b>{judge_name}</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )

    # Sudyaga PIN qilamiz
    try:
        await bot.pin_chat_message(game["chat_id"], msg.message_id)
    except Exception:
        pass


# ══════════════════════════════════════════════════════
#  !dalil — Dalil berish va taymer
# ══════════════════════════════════════════════════════

@router.message(F.text.startswith("!dalil"))
async def cmd_dalil(message: Message, bot: Bot):
    game = await get_active_game(message.chat.id)
    if not game or game["status"] != "active":
        return

    player = await get_player(game["game_id"], message.from_user.id)
    if not player or not player["is_alive"]:
        await message.reply("⛔ Siz o'yinda yo'qsiz!")
        return

    # Pristav bloki tekshiruvi
    if player["night_blocked"]:
        await message.reply(
            "🚫 <b>Siz sud zalidan chiqarilgansiz!</b>\n"
            "Bu raundda dalil bera olmaysiz.",
            parse_mode="HTML"
        )
        return

    team = player["team"]
    game_id = game["game_id"]

    # Har raundda faqat 1 ta dalil
    col_used = "white_dalil_used" if team == "white" else "black_dalil_used"
    if game[col_used]:
        await message.reply(
            f"⚠️ Jamoangiz bu raundda allaqachon dalil berdi!\n"
            "Keyingi raundni kuting.",
            parse_mode="HTML"
        )
        return

    dalil_text = message.text[6:].strip() or "(Matn yo'q)"
    team_label = "⚖️ OQ JAMOA" if team == "white" else "🖤 QORA JAMOA"

    caption = (
        f"📌 <b>DALIL TAQDIM ETILDI</b> — <b>{team_label}</b>\n\n"
        f"👤 <b>Kimdan:</b> {message.from_user.full_name}\n"
        f"🏷️ <b>Rol:</b> {player['role']}\n"
        f"💬 <b>Dalil:</b> {dalil_text}\n\n"
        f"⏳ Jamoa uchun <b>120 soniya</b> — shu vaqtda sharhlab bering!"
    )

    try:
        await bot.pin_chat_message(message.chat.id, message.message_id)
    except Exception:
        pass

    dalil_msg = await message.reply(caption, parse_mode="HTML")

    # Qarama-qarshi jamoani mute qilish, bu jamoaga so'z berish
    opposite = "black" if team == "white" else "white"
    await mute_team(bot, message.chat.id, game_id, opposite, True)
    await mute_team(bot, message.chat.id, game_id, team, False)

    # Dalil ishlatilganini belgilash
    await mark_dalil_used(game_id, team)

    # Old Document kartasi tekshiruvi
    await _apply_old_document_bonus(game_id, team)

    # 120 soniya taymer
    asyncio.create_task(
        _dalil_timer(bot, message.chat.id, game_id, dalil_msg.message_id, team)
    )


async def _apply_old_document_bonus(game_id: int, team: str):
    """'Eski sanali hujjat' kartasi — dalil berilganda +2 avtomatik qo'shiladi."""
    game = await get_game_by_id(game_id)
    players = await get_team_players(game_id, team)
    for p in players:
        purchases = await get_user_purchases(p["user_id"], unused_only=True)
        doc_card = next(
            (x for x in purchases if x["effect_code"] == "old_document"), None
        )
        if doc_card:
            await add_score(game_id, team, 2)
            await mark_item_used(doc_card["id"], game_id)
            logger.info(
                f"Eski sanali hujjat: {p['user_id']} jamoasiga +2 ball qo'shildi"
            )
            break  # bir marta yetarli


async def _dalil_timer(
    bot: Bot, chat_id: int, game_id: int,
    dalil_msg_id: int, team: str
):
    """120 soniya o'tgach, ikkala jamoani jim qiladi va ball berish panelini chiqaradi."""
    await asyncio.sleep(DALIL_TIMER_SECONDS)

    game = await get_game_by_id(game_id)
    if not game or game["status"] != "active":
        return

    await mute_all_players(bot, chat_id, game_id)

    # Ikkala dalil ishlatildimi? Ball berish vaqti!
    if game["white_dalil_used"] and game["black_dalil_used"]:
        try:
            await bot.send_message(
                chat_id,
                f"⏰ <b>Ikkala jamoa ham dalilini bildirdi!</b>\n\n"
                f"👨‍⚖️ Sudya, iltimos ball bering:",
                parse_mode="HTML",
                reply_markup=_scoring_kb(game_id)
            )
        except Exception as e:
            logger.warning(f"_dalil_timer xato: {e}")
    else:
        # Faqat bir jamoa dalil berdi — boshqa jamoani rag'batlantirish
        remaining = "black" if team == "white" else "white"
        label = "🖤 QORA JAMOA" if remaining == "black" else "⚖️ OQ JAMOA"
        try:
            await bot.send_message(
                chat_id,
                f"⏳ Taymer tugadi.\n{label} hali dalil bermadi.\n"
                f"<code>!dalil [matn]</code> bilan dalil bering!",
                parse_mode="HTML"
            )
            # Bu jamoaga so'z beramiz
            await mute_team(bot, chat_id, game_id, remaining, False)
            # Yana 120 soniya yangi taymer (faqat bir marta)
        except Exception:
            pass


# ══════════════════════════════════════════════════════
#  SUDYA TUGMALARI — Mikrofon boshqaruvi
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("unmute_white_"))
async def cb_unmute_white(call: CallbackQuery, bot: Bot):
    game_id = int(call.data.split("_")[2])
    game = await get_game_by_id(game_id)
    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya!", show_alert=True)
        return

    await update_judge_action_time(game_id)
    await mute_team(bot, game["chat_id"], game_id, "black", True)
    await mute_team(bot, game["chat_id"], game_id, "white", False)
    await set_current_turn(game_id, "white")
    await call.answer("✅ Oq jamoa mikrofoni ochildi!")
    await call.message.reply(
        "🎤 <b>So'z OQ JAMOAGA berildi!</b>",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("unmute_black_"))
async def cb_unmute_black(call: CallbackQuery, bot: Bot):
    game_id = int(call.data.split("_")[2])
    game = await get_game_by_id(game_id)
    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya!", show_alert=True)
        return

    await update_judge_action_time(game_id)
    await mute_team(bot, game["chat_id"], game_id, "white", True)
    await mute_team(bot, game["chat_id"], game_id, "black", False)
    await set_current_turn(game_id, "black")
    await call.answer("✅ Qora jamoa mikrofoni ochildi!")
    await call.message.reply(
        "🎤 <b>So'z QORA JAMOAGA berildi!</b>",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("mute_all_"))
async def cb_mute_all(call: CallbackQuery, bot: Bot):
    game_id = int(call.data.split("_")[2])
    game = await get_game_by_id(game_id)
    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya!", show_alert=True)
        return

    await update_judge_action_time(game_id)
    await mute_all_players(bot, game["chat_id"], game_id)
    await call.answer("🔇 Barcha jim qilindi!")
    await call.message.reply("🔇 <b>Barcha ishtirokchilar jim qilindi.</b>", parse_mode="HTML")


# ══════════════════════════════════════════════════════
#  BALL BERISH (SCORING) — Anti-cheat: faqat 1-5
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.regexp(r"^score_(white|black)_([1-5])_(\d+)$"))
async def cb_score(call: CallbackQuery, bot: Bot):
    import re
    match = re.match(r"^score_(white|black)_([1-5])_(\d+)$", call.data)
    team = match.group(1)
    points = int(match.group(2))
    game_id = int(match.group(3))

    game = await get_game_by_id(game_id)
    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya ball beradi!", show_alert=True)
        return

    # Anti-cheat: 1-5 oralig'ida (regex allaqachon ta'minlagan)
    if not (1 <= points <= 5):
        await call.answer("⛔ Ball 1-5 oralig'ida bo'lishi kerak!", show_alert=True)
        return

    await update_judge_action_time(game_id)
    await add_score(game_id, team, points)

    game_updated = await get_game_by_id(game_id)
    team_label = "⚖️ OQ JAMOA" if team == "white" else "🖤 QORA JAMOA"

    await call.message.reply(
        f"✅ <b>{team_label}</b> ga <b>+{points} ball</b> berildi!\n\n"
        f"📊 Umumiy: ⚖️ {game_updated['white_score']} | "
        f"🖤 {game_updated['black_score']}",
        parse_mode="HTML"
    )
    await call.answer(f"✅ +{points} ball berildi!")

    # Ikkala jamoaga ball berildimi? Keyingi raundga o'tish
    # Bu yerda sodda tekshiruv: Sudya har ikkala jamoaga ball bergach raund tugaydi
    # Amalda Sudya avval birga, keyin ikkinchiga ball beradi
    # Raund tugatish uchun "Raundni yakunlash" tugmasi qo'shamiz
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"➡️ Keyingi raundga o'tish",
                callback_data=f"next_round_{game_id}"
            )],
            [InlineKeyboardButton(
                text="⚖️ O'yinni yakunlash",
                callback_data=f"end_game_{game_id}"
            )]
        ]
    )
    await call.message.reply(
        f"👨‍⚖️ Ball berildi. Keyingi raundni boshlaysizmi?",
        reply_markup=kb
    )


# ══════════════════════════════════════════════════════
#  KEYINGI RAUNDGA O'TISH
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("next_round_"))
async def cb_next_round(call: CallbackQuery, bot: Bot):
    game_id = int(call.data.split("_")[2])
    game = await get_game_by_id(game_id)

    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya!", show_alert=True)
        return

    await update_judge_action_time(game_id)

    # Joriy raund balllarini saqlash
    await save_round_score(
        game_id, game["round_number"],
        game["white_score"], game["black_score"]
    )

    if game["round_number"] >= MAX_ROUNDS:
        # 5-raund tugadi — natijani tekshirish
        await _check_final_result(bot, call.message, game)
        await call.answer()
        return

    # Tun fazasiga o'tish
    await update_game_phase(game_id, "night")
    await mute_all_players(bot, game["chat_id"], game_id)
    await reset_night_statuses(game_id)

    await call.message.reply(
        f"🌙 <b>YOPIQ TERGOV BOSQICHI ({game['round_number']}/{MAX_ROUNDS})</b>\n\n"
        f"Tungi faoliyat vaqti!\n\n"
        f"🔍 Detektiv, Ekspert, Soxta Guvoh, Arxiv Xodimi va Pristav —\n"
        f"bot lichkasida o'z tungi buyrug'ingizni bajaring.\n\n"
        f"⏰ Tun 60 soniyadan so'ng tugaydi.",
        parse_mode="HTML"
    )

    # Har bir rol egasiga lichkada tun panelini yuborish
    await _send_night_panels(call.bot, game_id)

    # Tun taymeri
    asyncio.create_task(
        _night_timer(bot, game_id, game["chat_id"], call.message)
    )
    await call.answer()


async def _send_night_panels(bot: Bot, game_id: int):
    """Har bir rol egasiga lichkada tungi panel yuboradi."""
    players = await get_alive_players(game_id)
    game = await get_game_by_id(game_id)
    round_num = game["round_number"]

    for player in players:
        role = player["role"]
        role_info = ROLES.get(role, {})
        night_action = role_info.get("night_action")

        if not night_action:
            # Oddiy o'yinchilar uchun jamoa chati tugmasi
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="💬 Jamoa Maxfiy Chati",
                        callback_data=f"team_chat_{game_id}"
                    )
                ]]
            )
            try:
                await bot.send_message(
                    player["user_id"],
                    f"🌙 <b>TUN FAZASI — RAUND {round_num}</b>\n\n"
                    f"Sizning rolingiz: <b>{role}</b>\n"
                    f"Bu tun uchun maxsus vazifangiz yo'q.\n\n"
                    f"💬 Jamoangiz bilan maxfiy chat uchun:",
                    parse_mode="HTML",
                    reply_markup=kb
                )
            except Exception:
                pass
            continue

        # Rol-specific panellar
        alive = await get_alive_players(game_id)
        # Faqat boshqa o'yinchilar — o'zini tanlay olmaydi
        others = [p for p in alive if p["user_id"] != player["user_id"]]

        if not others:
            continue

        buttons = []
        for target in others:
            try:
                target_user = await bot.get_chat_member(
                    game["chat_id"], target["user_id"]
                )
                tname = target_user.user.full_name
            except Exception:
                tname = f"O'yinchi {target['user_id']}"

            buttons.append([
                InlineKeyboardButton(
                    text=f"🎯 {tname}",
                    callback_data=f"night_{night_action}_{game_id}_{target['user_id']}"
                )
            ])

        # Jamoa chati tugmasi ham qo'shamiz
        buttons.append([
            InlineKeyboardButton(
                text="💬 Jamoa Maxfiy Chati",
                callback_data=f"team_chat_{game_id}"
            )
        ])

        action_descriptions = {
            "detective":    "🔍 Qaysi o'yinchini tekshirmoqchisiz?",
            "forensic":     "🔬 Qaysi o'yinchining profilini tekshirmoqchisiz?",
            "fake_witness": "📝 Qaysi o'yinchi ustidan feyk ko'rsatma yozasiz?",
            "archive":      "🗂️ Qaysi sherigingizni bu kecha himoya qilasiz?",
            "bailiff":      "🚪 Qaysi o'yinchini su'd zalidan chiqarasiz?",
        }

        try:
            await bot.send_message(
                player["user_id"],
                f"🌙 <b>TUN FAZASI — RAUND {round_num}</b>\n\n"
                f"🎭 Rolingiz: <b>{role}</b>\n\n"
                f"{action_descriptions.get(night_action, 'Nishonni tanlang:')}\n"
                f"<i>(Bir marta tanlaysiz)</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
        except Exception as e:
            logger.warning(f"Tun panelini yuborishda xato ({player['user_id']}): {e}")


# ══════════════════════════════════════════════════════
#  TUN HARAKATLARI — Lichkadan callback
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.regexp(r"^night_(detective|forensic|fake_witness|archive|bailiff)_"))
async def cb_night_action(call: CallbackQuery, bot: Bot):
    import re
    match = re.match(
        r"^night_(detective|forensic|fake_witness|archive|bailiff)_(\d+)_(\d+)$",
        call.data
    )
    if not match:
        await call.answer("❌ Noto'g'ri format!", show_alert=True)
        return

    action_type = match.group(1)
    game_id = int(match.group(2))
    target_id = int(match.group(3))

    game = await get_game_by_id(game_id)
    if not game or game["phase"] != "night":
        await call.answer("⚠️ O'yin tun fazasida emas!", show_alert=True)
        return

    actor_id = call.from_user.id
    player = await get_player(game_id, actor_id)
    if not player or not player["is_alive"]:
        await call.answer("❌ Siz o'yinda yo'qsiz!", show_alert=True)
        return

    # Allaqachon harakat qilganmi?
    existing = await get_player_night_action(game_id, game["round_number"], actor_id)
    if existing:
        await call.answer("⚠️ Bu tun allaqachon harakat qildingiz!", show_alert=True)
        return

    # Uncle card (immunitet) tekshiruvi — Pristav va Archive uchun
    if action_type in ("bailiff", "archive"):
        target_player = await get_player(game_id, target_id)
        if target_player and target_player.get("has_immunity"):
            await call.answer(
                "🃏 Nishon 'Amakingizning vizitkasi' kartasiga ega — "
                "ta'siringiz bloklandi!",
                show_alert=True
            )
            return

    # Harakat turlariga qarab natija
    result = ""

    if action_type == "detective":
        target_player = await get_player(game_id, target_id)
        if target_player:
            # Arxiv himoyasini tekshirish
            if target_player.get("night_protected"):
                result = "Tizim: Bu shaxsning hujjatlari 'OQ' ko'rinadi. (Arxiv himoyasi)"
            else:
                team_label = "⚖️ OQ JAMOA" if target_player["team"] == "white" else "🖤 QORA JAMOA"
                result = f"Tekshirish natijasi: {team_label}"
        await call.answer("✅ Tekshiruv amalga oshirildi!")

    elif action_type == "forensic":
        target_player = await get_player(game_id, target_id)
        if target_player:
            result = (
                f"Rol: {target_player['role']} | "
                f"Jamoa: {'OQ' if target_player['team'] == 'white' else 'QORA'}"
            )
        await call.answer("✅ Profil tekshirildi!")

    elif action_type == "fake_witness":
        # Ertasi kuni guruhga e'lon qilinadi
        result = f"feyk_target:{target_id}"
        await call.answer("✅ Feyk ko'rsatma yozildi!")

    elif action_type == "archive":
        await set_night_protected(game_id, target_id, True)
        result = f"protected:{target_id}"
        await call.answer("✅ Sherigingiz himoyalandi!")

    elif action_type == "bailiff":
        await set_night_blocked(game_id, target_id, True)
        result = f"blocked:{target_id}"
        await call.answer("✅ O'yinchi sud zalidan chiqarildi!")

    # Harakatni saqlash
    await save_night_action(
        game_id, game["round_number"],
        actor_id, target_id, action_type, result
    )

    # Natijani lichkada ko'rsatish
    if result and action_type in ("detective", "forensic"):
        try:
            await call.bot.send_message(
                actor_id,
                f"🔍 <b>TUN NATIJASI</b>\n\n{result}",
                parse_mode="HTML"
            )
        except Exception:
            pass

    await call.message.edit_text(
        f"✅ Tungi harakatingiz qayd etildi.\n"
        f"Tun tugashini kuting.",
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════
#  JAMOA MAXFIY CHATI TUGMASI (lichkada)
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("team_chat_"))
async def cb_team_chat(call: CallbackQuery):
    game_id = int(call.data.split("_")[2])
    await call.message.answer(
        f"💬 <b>JAMOA MAXFIY CHATI</b>\n\n"
        f"Jamoangizga anonim xabar yuborish uchun:\n"
        f"<code>!jamoa_send [-{abs(game_id)}] [xabar]</code>\n\n"
        f"<i>Misol: !jamoa_send [-1001234567890] Keyingi raundda jimlik strategiyasi!</i>\n\n"
        f"Bot siz yuborganingizni hech kimga aytmaydi.",
        parse_mode="HTML"
    )
    await call.answer()


# ══════════════════════════════════════════════════════
#  TUN TAYMERI VA SABAH E'LONI
# ══════════════════════════════════════════════════════

async def _night_timer(
    bot: Bot, game_id: int, chat_id: int, last_message: Message
):
    """60 soniya kutadi, keyin tun harakatlarini qayta ishlaydi."""
    await asyncio.sleep(60)

    game = await get_game_by_id(game_id)
    if not game or game["phase"] != "night":
        return

    # Tungi harakatlarni qayta ishlash
    morning_announcements = []
    actions = await get_night_actions(game_id, game["round_number"])

    for action in actions:
        if action["action_type"] == "fake_witness":
            # Feyk ko'rsatmani guruhga e'lon qilamiz
            target_id = int(action["result_data"].split(":")[1])
            try:
                target_member = await bot.get_chat_member(chat_id, target_id)
                tname = target_member.user.full_name
            except Exception:
                tname = f"O'yinchi {target_id}"
            morning_announcements.append(
                f"🗣️ <b>Guvoh:</b> «{tname} shubhali harakatlar qilmoqda»"
            )
            await mark_night_action_processed(action["id"])

        elif action["action_type"] == "bailiff":
            target_id = int(action["result_data"].split(":")[1])
            morning_announcements.append(
                f"🚪 Bir ishtirokchi <b>kelasi raundda gapira olmaydi</b> (sud pristavi amri)"
            )
            await mark_night_action_processed(action["id"])

    # Raundni oshirib kunduz fazasiga o'tish
    await increment_round(game_id)
    await update_game_phase(game_id, "day")

    game_new = await get_game_by_id(game_id)
    announce_text = (
        f"🌅 <b>YANGI KUN BOSHLANDI — RAUND {game_new['round_number']}/{MAX_ROUNDS}</b>\n\n"
    )
    if morning_announcements:
        announce_text += "📰 <b>Tun davomida sodir bo'lgan hodisalar:</b>\n"
        announce_text += "\n".join(morning_announcements) + "\n\n"

    announce_text += (
        f"📊 <b>Joriy hisoblar:</b>\n"
        f"⚖️ Oq jamoa: <b>{game_new['white_score']}</b>\n"
        f"🖤 Qora jamoa: <b>{game_new['black_score']}</b>"
    )

    try:
        await bot.send_message(
            chat_id,
            announce_text,
            parse_mode="HTML",
            reply_markup=_judge_main_kb(game_id)
        )
    except Exception as e:
        logger.error(f"_night_timer sabah e'loni xatosi: {e}")


# ══════════════════════════════════════════════════════
#  5-RAUND OXIRI — YAKUNIY NATIJA
# ══════════════════════════════════════════════════════

async def _check_final_result(bot: Bot, message: Message, game: dict):
    """5-raund tugagach g'olibni aniqlab, jazolarni qo'llaydi."""
    game_id = game["game_id"]
    w = game["white_score"]
    b = game["black_score"]

    if w == b:
        # DURANG — Sudya hal qiladi
        await message.reply(
            f"⚖️ <b>5-RAUND TUGADI!</b>\n\n"
            f"📊 <b>Yakuniy hisoblar:</b>\n"
            f"⚖️ Oq jamoa: <b>{w}</b>\n"
            f"🖤 Qora jamoa: <b>{b}</b>\n\n"
            f"🟡 <b>DURANG!</b>\n\n"
            f"👨‍⚖️ Sudya, siz yakuniy verdiktni chiqarasiz:",
            parse_mode="HTML",
            reply_markup=_verdict_kb(game_id)
        )
    elif w > b:
        await _finish_game(bot, message, game, "white")
    else:
        await _finish_game(bot, message, game, "black")


@router.callback_query(F.data.startswith("verdict_"))
async def cb_verdict(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    result = parts[1]   # "white" | "black"
    game_id = int(parts[2])

    game = await get_game_by_id(game_id)
    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya yakuniy verdikt chiqaradi!", show_alert=True)
        return

    await call.answer("✅ Verdikt berildi!")
    await _finish_game(bot, call.message, game, result)


# ══════════════════════════════════════════════════════
#  O'YINNI YAKUNLASH
# ══════════════════════════════════════════════════════

async def _finish_game(
    bot: Bot, message: Message, game: dict, winning_team: str
):
    """
    G'olibni e'lon qiladi, jazolarni qo'llaydi,
    Real Ayblanuvchini mute qiladi (bail tekshiruvi bilan).
    """
    game_id = game["game_id"]
    loser_team = "black" if winning_team == "white" else "white"

    # G'oliblarni mukofotlash
    winner_ids = await reward_winners(game_id, winning_team, coins=250, rating_bonus=50)
    # Mag'lublarga jarima
    await penalize_losers(game_id, loser_team, rating_penalty=25)

    # Real Ayblanuvchi jazosi
    accused_muted = False
    accused_id = game.get("accused_user_id")
    accused_label = ""

    if winning_team == "black" and accused_id:
        # Qoralar yutdi = Ayblanuvchi mute bo'ladi
        # Bail card tekshiruvi
        accused_player = await get_player(game_id, accused_id)
        has_bail = accused_player.get("has_bail", 0) if accused_player else 0

        if not has_bail:
            # Bail card bor/yo'qligini DB purchases'dan ham tekshiramiz
            purchases = await get_user_purchases(accused_id, unused_only=True)
            bail_card = next(
                (p for p in purchases if p["effect_code"] == "bail_contract"), None
            )
            if bail_card:
                await mark_item_used(bail_card["id"], game_id)
                accused_label = (
                    f"\n\n📋 <b>Kafillik shartnomasi</b> ishladi! "
                    f"Ayblanuvchi <a href='tg://user?id={accused_id}'>bu shaxs</a> "
                    f"jazosiz qoldi!"
                )
            else:
                # Haqiqiy mute
                try:
                    until_date = datetime.utcnow() + timedelta(minutes=MUTE_DURATION_MINUTES)
                    await bot.restrict_chat_member(
                        chat_id=game["chat_id"],
                        user_id=accused_id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until_date
                    )
                    accused_muted = True
                    try:
                        await bot.send_message(
                            accused_id,
                            f"⛓️ <b>HUKM IJRO ETILDI!</b>\n\n"
                            f"Siz {MUTE_DURATION_MINUTES} daqiqaga guruhda mute qilindingiz!\n"
                            f"<i>O'yin #{game_id} — Qoralar jamoasi g'alaba qozondi.</i>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Mute qilishda xato: {e}")
        else:
            accused_label = (
                f"\n\n🛡️ Ayblanuvchi <a href='tg://user?id={accused_id}'>bu shaxs</a> "
                f"kafillik shartnomasi bilan jazosiz qoldi!"
            )

    # Guruhni ochish
    await update_game_status(game_id, "finished")
    await unfreeze_chat(bot, game["chat_id"])
    await update_game_phase(game_id, "finished")

    # G'oliblar mention
    winner_mentions = " ".join([
        f"<a href='tg://user?id={uid}'>🏆</a>" for uid in winner_ids
    ])
    team_emoji = "⚖️ OQ" if winning_team == "white" else "🖤 QORA"

    result_text = (
        f"🎉 <b>SUD MAJLISI YAKUNLANDI!</b>\n\n"
        f"🏆 <b>G'OLIB: {team_emoji} JAMOA!</b>\n\n"
        f"{winner_mentions}\n\n"
        f"📊 <b>Yakuniy hisoblar:</b>\n"
        f"⚖️ Oq jamoa: <b>{game['white_score']}</b>\n"
        f"🖤 Qora jamoa: <b>{game['black_score']}</b>\n\n"
        f"💰 Har g'olibga: <b>+250 Court Coins</b> va <b>+50 Reyting</b>\n"
        f"📉 Mag'lublar: <b>-25 Reyting</b>"
    )

    if accused_muted:
        result_text += (
            f"\n\n⛓️ Real Ayblanuvchi <a href='tg://user?id={accused_id}'>bu shaxs</a> "
            f"{MUTE_DURATION_MINUTES} daqiqaga mute qilindi!"
        )
    result_text += accused_label

    # Karma tugmasi
    kb = _karma_kb(game_id, game["judge_id"])

    await message.reply(
        result_text,
        parse_mode="HTML",
        reply_markup=kb
    )


# ══════════════════════════════════════════════════════
#  O'YINNI YAKUNLASH (Sudya tugmasi)
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("end_game_"))
async def cb_end_game(call: CallbackQuery, bot: Bot):
    game_id = int(call.data.split("_")[2])
    game = await get_game_by_id(game_id)
    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya yakunlay oladi!", show_alert=True)
        return

    await update_judge_action_time(game_id)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚖️ Oq jamoa g'alaba",
                    callback_data=f"winner_white_{game_id}"
                ),
                InlineKeyboardButton(
                    text="🖤 Qora jamoa g'alaba",
                    callback_data=f"winner_black_{game_id}"
                ),
            ]
        ]
    )
    await call.message.reply(
        "⚖️ <b>O'yin yakunlanmoqda!</b>\nQaysi jamoa g'alaba qozondi?",
        parse_mode="HTML",
        reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data.startswith("winner_"))
async def cb_winner(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    team = parts[1]
    game_id = int(parts[2])

    game = await get_game_by_id(game_id)
    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya!", show_alert=True)
        return

    await call.answer("✅ O'yin yakunlandi!")
    await _finish_game(bot, call.message, game, team)


# ══════════════════════════════════════════════════════
#  KARMA TIZIMI
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.regexp(r"^karma_(plus|minus)_(\d+)_(\d+)$"))
async def cb_karma(call: CallbackQuery):
    import re
    match = re.match(r"^karma_(plus|minus)_(\d+)_(\d+)$", call.data)
    direction = match.group(1)
    game_id = int(match.group(2))
    judge_id = int(match.group(3))

    vote = 1 if direction == "plus" else -1
    success = await cast_karma_vote(game_id, judge_id, call.from_user.id, vote)

    if success:
        emoji = "👍" if direction == "plus" else "👎"
        await call.answer(
            f"{emoji} Sudya reytingiga ovoz berdingiz!",
            show_alert=True
        )
    else:
        await call.answer("⚠️ Siz allaqachon ovoz bergansiz!", show_alert=True)


# ══════════════════════════════════════════════════════
#  /arz_sudya — Impechment tizimi
# ══════════════════════════════════════════════════════

@router.message(Command("arz_sudya"))
async def cmd_arz_sudya(message: Message, bot: Bot):
    if message.chat.type not in ("group", "supergroup"):
        return

    game = await get_active_game(message.chat.id)
    if not game or game["status"] != "active":
        await message.reply("❌ Faol o'yin topilmadi.")
        return

    # Cooldown tekshiruvi
    can_vote = await check_ariza_cooldown(message.from_user.id, 60)
    if not can_vote:
        await message.reply(
            "⏳ /arz_sudya buyrug'ini qayta ishlating: <b>60 soniya</b> kutish kerak.",
            parse_mode="HTML"
        )
        return

    await update_ariza_cooldown(message.from_user.id)

    # Impechment ovozi
    total_votes = await cast_impeachment_vote(game["game_id"], message.from_user.id)

    if total_votes == -1:
        await message.reply("⚠️ Siz allaqachon ovoz bergansiz!")
        return

    # 50% dan ko'p ovoz kerak
    alive_players = await get_alive_players(game["game_id"])
    threshold = max(1, len(alive_players) // 2)

    await message.reply(
        f"🗳️ <b>Sudyaga qarshi ovozlar: {total_votes}/{threshold}</b>\n"
        f"(50% dan ko'p bo'lsa sudya almashtiriladi)",
        parse_mode="HTML"
    )

    if total_votes >= threshold:
        await _execute_impeachment(bot, message, game)


async def _execute_impeachment(bot: Bot, message: Message, game: dict):
    """Sudyani almashtirib, o'yinni davom ettiradi."""
    game_id = game["game_id"]
    old_judge_id = game["judge_id"]

    # Tirik o'yinchilar ichidan random yangi sudya
    alive = await get_alive_players(game_id)
    candidates = [p for p in alive if p["user_id"] != old_judge_id]

    if not candidates:
        await message.reply("❌ Yangi sudya uchun kandidat topilmadi.")
        return

    new_judge = random.choice(candidates)
    new_judge_id = new_judge["user_id"]

    await transfer_judge(game_id, new_judge_id)

    try:
        new_judge_member = await bot.get_chat_member(game["chat_id"], new_judge_id)
        nname = new_judge_member.user.full_name
    except Exception:
        nname = f"O'yinchi {new_judge_id}"

    await message.reply(
        f"⚡ <b>SUDYA ALMASHTIRILDI!</b>\n\n"
        f"Eski sudya iste'foga chiqarildi.\n"
        f"Yangi Sudya: <a href='tg://user?id={new_judge_id}'>{nname}</a>\n\n"
        f"O'yin to'xtovsiz davom etadi.",
        parse_mode="HTML"
    )

    # Yangi sudyaga lichkada xabar
    try:
        await bot.send_message(
            new_judge_id,
            f"⚖️ <b>SIZ YANGI SUDYA SIFATIDA TAYINLANDINGIZ!</b>\n\n"
            f"O'yin #{game_id} davom etmoqda.\n"
            f"Guruhga qayting va boshqaruv panelini ishlating.",
            parse_mode="HTML"
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════
#  AFK WATCHER — Sudya 3 daqiqada javob bermasa
# ══════════════════════════════════════════════════════

async def _afk_watcher(bot: Bot, game_id: int, chat_id: int):
    """
    Har 60 soniyada Sudyaning so'nggi harakatini tekshiradi.
    3 daqiqa AFK bo'lsa — impechment ishga tushadi.
    """
    while True:
        await asyncio.sleep(60)

        game = await get_game_by_id(game_id)
        if not game or game["status"] != "active":
            break  # O'yin tugagan

        last_action = game.get("judge_last_action")
        if not last_action:
            continue

        try:
            last_dt = datetime.fromisoformat(last_action)
        except Exception:
            continue

        diff = (datetime.utcnow() - last_dt).total_seconds()

        if diff >= AFK_SECONDS:
            # Sudya AFK — avtomatik impechment
            try:
                await bot.send_message(
                    chat_id,
                    f"⏰ <b>Sudya {AFK_SECONDS // 60} daqiqadan ortiq javob bermadi!</b>\n\n"
                    f"Avtomatik sudya almashtirish boshlanyapti...",
                    parse_mode="HTML"
                )
            except Exception:
                pass

            # Fake message ob'ekti yaratamiz (impechment uchun)
            alive = await get_alive_players(game_id)
            candidates = [
                p for p in alive if p["user_id"] != game["judge_id"]
            ]
            if candidates:
                new_judge = random.choice(candidates)
                await transfer_judge(game_id, new_judge["user_id"])
                try:
                    m = await bot.get_chat_member(chat_id, new_judge["user_id"])
                    nname = m.user.full_name
                except Exception:
                    nname = f"O'yinchi {new_judge['user_id']}"

                try:
                    await bot.send_message(
                        chat_id,
                        f"⚡ Yangi Sudya: "
                        f"<a href='tg://user?id={new_judge['user_id']}'>{nname}</a>"
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            break  # Watcher tugaydi


# ══════════════════════════════════════════════════════
#  SUDYA TUN BOSQICHINI BOSHLASH
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("start_night_"))
async def cb_start_night(call: CallbackQuery, bot: Bot):
    game_id = int(call.data.split("_")[2])
    game = await get_game_by_id(game_id)
    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya!", show_alert=True)
        return

    await update_judge_action_time(game_id)

    if game["round_number"] >= MAX_ROUNDS:
        await _check_final_result(bot, call.message, game)
        await call.answer()
        return

    # Joriy raund balllarini saqlash
    await save_round_score(
        game_id, game["round_number"],
        game["white_score"], game["black_score"]
    )

    await update_game_phase(game_id, "night")
    await mute_all_players(bot, game["chat_id"], game_id)
    await reset_night_statuses(game_id)

    await call.message.reply(
        f"🌙 <b>YOPIQ TERGOV BOSHLANDI!</b>\n\n"
        f"Raund {game['round_number']} balllar:\n"
        f"⚖️ Oq: <b>{game['white_score']}</b> | "
        f"🖤 Qora: <b>{game['black_score']}</b>\n\n"
        f"Rol egalari lichkada harakatlarini bajarsin.\n"
        f"⏰ 60 soniyadan so'ng yangi kun boshlanadi.",
        parse_mode="HTML"
    )

    await _send_night_panels(call.bot, game_id)
    asyncio.create_task(
        _night_timer(bot, game_id, game["chat_id"], call.message)
    )
    await call.answer()


# ══════════════════════════════════════════════════════
#  ARIZA — Sudyaga ariza yuborish (guruhdan)
# ══════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("approve_ariza_"))
async def cb_approve_ariza(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    game_id = int(parts[2])
    user_id = int(parts[3])

    game = await get_game_by_id(game_id)
    if not game or call.from_user.id != game["judge_id"]:
        await call.answer("⛔ Faqat Sudya tasdiqlaydi!", show_alert=True)
        return

    await approve_ariza(game_id, user_id)
    await allow_write_for_player(bot, game["chat_id"], user_id)
    await call.answer("✅ Ariza tasdiqlandi!")
    await call.message.edit_text(
        call.message.text + "\n\n✅ <b>TASDIQLANDI</b>",
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════
#  /my_game_id — O'yin chat ID si
# ══════════════════════════════════════════════════════

@router.message(Command("my_game_id"))
async def cmd_my_game_id(message: Message):
    if message.chat.type in ("group", "supergroup"):
        await message.reply(
            f"🆔 <b>Guruh Chat ID:</b> <code>{message.chat.id}</code>\n"
            f"Bu ID ni inventar kartalarini ishlatishda ishlating.",
            parse_mode="HTML"
        )


# ══════════════════════════════════════════════════════
#  /end_court — Majburiy to'xtatish
# ══════════════════════════════════════════════════════

@router.message(Command("end_court"))
async def cmd_end_court(message: Message, bot: Bot):
    if message.chat.type not in ("group", "supergroup"):
        return

    game = await get_active_game(message.chat.id)
    if not game:
        await message.reply("❌ Faol o'yin yo'q.")
        return

    # Faqat sudya yoki guruh admini to'xtata oladi
    if message.from_user.id != game["judge_id"]:
        try:
            member = await bot.get_chat_member(
                message.chat.id, message.from_user.id
            )
            if member.status not in ("administrator", "creator"):
                await message.reply("⛔ Faqat Sudya yoki guruh admini!")
                return
        except Exception:
            await message.reply("⛔ Faqat Sudya yoki guruh admini!")
            return

    await update_game_status(game["game_id"], "finished")
    await unfreeze_chat(bot, message.chat.id)
    await message.reply(
        "🏛️ <b>O'yin majburiy ravishda to'xtatildi.</b>\n"
        "Guruh chati ochildi.",
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════
#  XATO USHLAGICH — Guruhni tark etish
# ══════════════════════════════════════════════════════

@router.message(F.left_chat_member)
async def on_member_left(message: Message, bot: Bot):
    """O'yinchi guruhni tark etsa, ularni o'yindan chiqaramiz."""
    if not message.left_chat_member:
        return

    user_id = message.left_chat_member.id
    game = await get_active_game(message.chat.id)

    if not game:
        return

    player = await get_player(game["game_id"], user_id)
    if not player or not player["is_alive"]:
        return

    await eliminate_player(game["game_id"], user_id)
    logger.info(
        f"O'yinchi {user_id} guruhni tark etdi, o'yindan chiqarildi. "
        f"Game ID: {game['game_id']}"
    )
