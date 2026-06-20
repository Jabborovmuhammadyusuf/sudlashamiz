# database/db_main.py
# Sud Tizimi — To'liq yangilangan ma'lumotlar bazasi moduli
# Yangiliklar: game_scores, night_actions, player_items, karma,
#              ariza_cooldown, yangi ustunlar, impechment, rollar tizimi

import aiosqlite
import logging
from typing import Optional

logger = logging.getLogger(__name__)
DB_PATH = "sud_tizimi.db"


# ══════════════════════════════════════════════════════
#  JADVALLARNI YARATISH
# ══════════════════════════════════════════════════════

async def create_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            -- Foydalanuvchilar
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                coins       INTEGER DEFAULT 0,
                rating      INTEGER DEFAULT 1000,
                karma       INTEGER DEFAULT 0,
                registered  TEXT    DEFAULT (datetime('now'))
            );

            -- O'yinlar (kengaytirilgan)
            CREATE TABLE IF NOT EXISTS games (
                game_id             INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id             INTEGER NOT NULL,
                status              TEXT    DEFAULT 'waiting',
                -- waiting | active | night | finished
                phase               TEXT    DEFAULT 'waiting',
                -- waiting | registration | day | night | scoring | finished
                judge_id            INTEGER,
                current_turn        TEXT    DEFAULT 'white',
                round_number        INTEGER DEFAULT 1,
                white_score         INTEGER DEFAULT 0,
                black_score         INTEGER DEFAULT 0,
                accused_user_id     INTEGER,
                -- Real Ayblanuvchi
                ish_mavzusi         TEXT,
                voice_chat_verified INTEGER DEFAULT 0,
                text_mode           INTEGER DEFAULT 0,
                -- 1 = matnli rejim
                voice_warn_count    INTEGER DEFAULT 0,
                -- 0-3 ogohlantirish
                white_dalil_used    INTEGER DEFAULT 0,
                -- shu raundda ishlatilganmi
                black_dalil_used    INTEGER DEFAULT 0,
                white_scored        INTEGER DEFAULT 0,
                -- shu raundda Sudya Oqlarga ball berdimi (anti-duplicate)
                black_scored        INTEGER DEFAULT 0,
                -- shu raundda Sudya Qoralarga ball berdimi (anti-duplicate)
                judge_last_action   TEXT    DEFAULT (datetime('now')),
                -- AFK tekshiruvi uchun
                created_at          TEXT    DEFAULT (datetime('now')),
                finished_at         TEXT
            );

            -- O'yinchilar (kengaytirilgan)
            CREATE TABLE IF NOT EXISTS players (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id             INTEGER NOT NULL REFERENCES games(game_id),
                user_id             INTEGER NOT NULL REFERENCES users(user_id),
                team                TEXT    NOT NULL,
                role                TEXT,
                is_alive            INTEGER DEFAULT 1,
                muted               INTEGER DEFAULT 1,
                night_blocked       INTEGER DEFAULT 0,
                -- Pristav tomonidan bloklanganmi
                night_protected     INTEGER DEFAULT 0,
                -- Arxiv tomonidan himoyalanganmi
                has_immunity        INTEGER DEFAULT 0,
                -- "Amakingizning vizitkasi" kartasi
                has_bail            INTEGER DEFAULT 0,
                -- "Kafillik shartnomasi" kartasi
                ariza_text          TEXT,
                ariza_approved      INTEGER DEFAULT 0,
                UNIQUE(game_id, user_id)
            );

            -- Raund ballari (har raund uchun alohida yozuv)
            CREATE TABLE IF NOT EXISTS round_scores (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id         INTEGER NOT NULL REFERENCES games(game_id),
                round_number    INTEGER NOT NULL,
                white_points    INTEGER DEFAULT 0,
                black_points    INTEGER DEFAULT 0,
                scored_at       TEXT    DEFAULT (datetime('now'))
            );

            -- Tungi harakatlar (rollarning tunda bajariladigan amallari)
            CREATE TABLE IF NOT EXISTS night_actions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id         INTEGER NOT NULL REFERENCES games(game_id),
                round_number    INTEGER NOT NULL,
                actor_id        INTEGER NOT NULL,
                -- harakat qiluvchi
                target_id       INTEGER,
                -- nishon
                action_type     TEXT    NOT NULL,
                -- detective | forensic | fake_witness | archive | bailiff
                result_data     TEXT,
                -- JSON yoki matn
                processed       INTEGER DEFAULT 0,
                -- 0=yangi, 1=ishlov berilgan
                created_at      TEXT    DEFAULT (datetime('now'))
            );

            -- Do'kon tovarlari
            CREATE TABLE IF NOT EXISTS shop_items (
                item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                description TEXT,
                price       INTEGER NOT NULL,
                effect_code TEXT    NOT NULL,
                is_active   INTEGER DEFAULT 1
            );

            -- Xaridlar
            CREATE TABLE IF NOT EXISTS purchases (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(user_id),
                item_id     INTEGER NOT NULL REFERENCES shop_items(item_id),
                game_id     INTEGER,
                -- qaysi o'yinda ishlatilganmi
                bought_at   TEXT    DEFAULT (datetime('now')),
                used        INTEGER DEFAULT 0,
                used_at     TEXT
            );

            -- Ariza cooldown (spam oldini olish)
            CREATE TABLE IF NOT EXISTS ariza_cooldown (
                user_id     INTEGER PRIMARY KEY,
                last_ariza  TEXT    DEFAULT (datetime('now'))
            );

            -- Karma (o'yin oxirida sudyani baholash)
            CREATE TABLE IF NOT EXISTS karma_votes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id     INTEGER NOT NULL,
                judge_id    INTEGER NOT NULL,
                voter_id    INTEGER NOT NULL,
                vote        INTEGER NOT NULL,
                -- +1 yoki -1
                voted_at    TEXT    DEFAULT (datetime('now')),
                UNIQUE(game_id, voter_id)
                -- bir o'yinchidan faqat 1 ovoz
            );

            -- Jamoa maxfiy chat echo logi
            CREATE TABLE IF NOT EXISTS team_chat_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id     INTEGER NOT NULL,
                sender_id   INTEGER NOT NULL,
                team        TEXT    NOT NULL,
                message_text TEXT,
                sent_at     TEXT    DEFAULT (datetime('now'))
            );
        """)
        await db.commit()
    logger.info("Barcha jadvallar tayyor.")


# ══════════════════════════════════════════════════════
#  USERS
# ══════════════════════════════════════════════════════

async def register_user(user_id: int, username: Optional[str], full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name
        """, (user_id, username, full_name))
        await db.commit()


async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_coins(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()


async def deduct_coins(user_id: int, amount: int) -> bool:
    """Coinlarni ayiradi. Yetarli bo'lmasa False qaytaradi."""
    user = await get_user(user_id)
    if not user or user["coins"] < amount:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins - ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()
    return True


async def get_coins(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT coins FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def add_rating(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET rating = MAX(0, rating + ?) WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()


async def get_rating(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT rating FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 1000


# ══════════════════════════════════════════════════════
#  GAMES
# ══════════════════════════════════════════════════════

async def create_game(chat_id: int, judge_id: int, ish_mavzusi: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO games (chat_id, judge_id, ish_mavzusi) VALUES (?, ?, ?)",
            (chat_id, judge_id, ish_mavzusi)
        )
        await db.commit()
        return cur.lastrowid


async def get_active_game(chat_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM games
               WHERE chat_id = ? AND status != 'finished'
               ORDER BY game_id DESC LIMIT 1""",
            (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_game_by_id(game_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM games WHERE game_id = ?", (game_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_game_status(game_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        if status == "finished":
            await db.execute(
                "UPDATE games SET status = ?, phase = 'finished', "
                "finished_at = datetime('now') WHERE game_id = ?",
                (status, game_id)
            )
        else:
            await db.execute(
                "UPDATE games SET status = ? WHERE game_id = ?",
                (status, game_id)
            )
        await db.commit()


async def update_game_phase(game_id: int, phase: str):
    """Faza: waiting | registration | day | night | scoring | finished"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET phase = ? WHERE game_id = ?",
            (phase, game_id)
        )
        await db.commit()


async def set_current_turn(game_id: int, team: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET current_turn = ? WHERE game_id = ?",
            (team, game_id)
        )
        await db.commit()


async def increment_round(game_id: int):
    """
    Keyingi raundga o'tkazadi VA shu raundga tegishli barcha
    bayroqlarni (dalil, ball) tozalaydi.
    MUHIM: bu funksiya chaqirilmasa, eski 'dalil_used'/'scored'
    bayroqlari qoladi va keyingi raundda hech kim dalil/ball
    bera olmay qoladi — shuning uchun har joyda (next_round,
    start_night, night_timer) albatta shu funksiya orqali o'tiladi.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET round_number = round_number + 1, "
            "white_dalil_used = 0, black_dalil_used = 0, "
            "white_scored = 0, black_scored = 0 "
            "WHERE game_id = ?",
            (game_id,)
        )
        await db.commit()


async def reset_round_flags(game_id: int):
    """Joriy raund uchun dalil/ball bayroqlarini (raund raqamini oshirmasdan) tozalaydi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET white_dalil_used = 0, black_dalil_used = 0, "
            "white_scored = 0, black_scored = 0 WHERE game_id = ?",
            (game_id,)
        )
        await db.commit()


async def set_accused(game_id: int, user_id: int):
    """Real Ayblanuvchini belgilash."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET accused_user_id = ? WHERE game_id = ?",
            (user_id, game_id)
        )
        await db.commit()


async def set_voice_chat_verified(game_id: int, verified: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET voice_chat_verified = ? WHERE game_id = ?",
            (1 if verified else 0, game_id)
        )
        await db.commit()


async def set_text_mode(game_id: int, enabled: bool):
    """Matnli rejimni yoqish/o'chirish."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET text_mode = ? WHERE game_id = ?",
            (1 if enabled else 0, game_id)
        )
        await db.commit()


async def increment_voice_warn(game_id: int) -> int:
    """Ovozli chat ogohlantirishini oshiradi, yangi qiymatni qaytaradi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET voice_warn_count = voice_warn_count + 1 WHERE game_id = ?",
            (game_id,)
        )
        await db.commit()
    game = await get_game_by_id(game_id)
    return game["voice_warn_count"] if game else 0


async def update_judge_action_time(game_id: int):
    """Sudyaning so'nggi harakat vaqtini yangilash (AFK oldini olish)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET judge_last_action = datetime('now') WHERE game_id = ?",
            (game_id,)
        )
        await db.commit()


async def transfer_judge(game_id: int, new_judge_id: int):
    """Sudyani yangi foydalanuvchiga o'tkazish (impechment)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET judge_id = ?, judge_last_action = datetime('now') "
            "WHERE game_id = ?",
            (new_judge_id, game_id)
        )
        await db.commit()


async def mark_dalil_used(game_id: int, team: str):
    """Shu raundda jamoa dalil ishlatganini belgilash."""
    col = "white_dalil_used" if team == "white" else "black_dalil_used"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE games SET {col} = 1 WHERE game_id = ?",
            (game_id,)
        )
        await db.commit()


async def add_score(game_id: int, team: str, points: int) -> bool:
    """
    Jamoaga ball qo'shadi — FAQAT shu raundda hali ball berilmagan bo'lsa.
    Anti-duplicate: bir jamoaga bir raundda faqat 1 marta ball berish mumkin.
    Qaytaradi: True = muvaffaqiyatli qo'shildi, False = bu raundda allaqachon ball berilgan.
    """
    score_col = "white_score" if team == "white" else "black_score"
    scored_col = "white_scored" if team == "white" else "black_scored"

    game = await get_game_by_id(game_id)
    if not game:
        return False
    if game.get(scored_col):
        return False  # bu raundda allaqachon ball berilgan — qayta berib bo'lmaydi

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE games SET {score_col} = {score_col} + ?, {scored_col} = 1 "
            f"WHERE game_id = ?",
            (points, game_id)
        )
        await db.commit()
    return True


async def add_bonus_score(game_id: int, team: str, points: int):
    """
    Karta effektlari (masalan 'Eski sanali hujjat') uchun ball qo'shadi.
    add_score()'dan farqi: bu funksiya 'scored' bayrog'iga tegmaydi,
    shuning uchun Sudya hali ham keyinroq o'z ballini bera oladi —
    aks holda bonus karta Sudyaning ball berish imkoniyatini bloklab qo'yardi.
    """
    score_col = "white_score" if team == "white" else "black_score"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE games SET {score_col} = {score_col} + ? WHERE game_id = ?",
            (points, game_id)
        )
        await db.commit()


async def both_teams_scored(game_id: int) -> bool:
    """Joriy raundda ikkala jamoaga ham ball berilganmi?"""
    game = await get_game_by_id(game_id)
    if not game:
        return False
    return bool(game.get("white_scored")) and bool(game.get("black_scored"))


async def save_round_score(game_id: int, round_num: int,
                           white_pts: int, black_pts: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO round_scores "
            "(game_id, round_number, white_points, black_points) VALUES (?, ?, ?, ?)",
            (game_id, round_num, white_pts, black_pts)
        )
        await db.commit()


async def get_round_scores(game_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM round_scores WHERE game_id = ? ORDER BY round_number ASC",
            (game_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ══════════════════════════════════════════════════════
#  PLAYERS
# ══════════════════════════════════════════════════════

async def add_player(game_id: int, user_id: int, team: str, role: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO players (game_id, user_id, team, role) "
            "VALUES (?, ?, ?, ?)",
            (game_id, user_id, team, role)
        )
        await db.commit()


async def get_players(game_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE game_id = ?", (game_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_alive_players(game_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE game_id = ? AND is_alive = 1",
            (game_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_team_players(game_id: int, team: str) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE game_id = ? AND team = ? AND is_alive = 1",
            (game_id, team)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_player(game_id: int, user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE game_id = ? AND user_id = ?",
            (game_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def set_player_mute(game_id: int, user_id: int, muted: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET muted = ? WHERE game_id = ? AND user_id = ?",
            (1 if muted else 0, game_id, user_id)
        )
        await db.commit()


async def set_team_mute(game_id: int, team: str, muted: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET muted = ? "
            "WHERE game_id = ? AND team = ? AND is_alive = 1",
            (1 if muted else 0, game_id, team)
        )
        await db.commit()


async def eliminate_player(game_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET is_alive = 0, muted = 1 "
            "WHERE game_id = ? AND user_id = ?",
            (game_id, user_id)
        )
        await db.commit()


async def set_night_blocked(game_id: int, user_id: int, blocked: bool):
    """Pristav tomonidan bir kecha bloklash."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET night_blocked = ? WHERE game_id = ? AND user_id = ?",
            (1 if blocked else 0, game_id, user_id)
        )
        await db.commit()


async def set_night_protected(game_id: int, user_id: int, protected: bool):
    """Arxiv tomonidan bir kecha himoya."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET night_protected = ? WHERE game_id = ? AND user_id = ?",
            (1 if protected else 0, game_id, user_id)
        )
        await db.commit()


async def set_player_immunity(game_id: int, user_id: int, has_immunity: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET has_immunity = ? WHERE game_id = ? AND user_id = ?",
            (1 if has_immunity else 0, game_id, user_id)
        )
        await db.commit()


async def set_player_bail(game_id: int, user_id: int, has_bail: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET has_bail = ? WHERE game_id = ? AND user_id = ?",
            (1 if has_bail else 0, game_id, user_id)
        )
        await db.commit()


async def reset_night_statuses(game_id: int):
    """Har kecha boshida tungi statuslarni tozalash."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET night_blocked = 0, night_protected = 0 "
            "WHERE game_id = ?",
            (game_id,)
        )
        await db.commit()


async def save_ariza(game_id: int, user_id: int, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET ariza_text = ?, ariza_approved = 0 "
            "WHERE game_id = ? AND user_id = ?",
            (text, game_id, user_id)
        )
        await db.commit()


async def approve_ariza(game_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET ariza_approved = 1 "
            "WHERE game_id = ? AND user_id = ?",
            (game_id, user_id)
        )
        await db.commit()


async def get_pending_arizalar(game_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players "
            "WHERE game_id = ? AND ariza_text IS NOT NULL AND ariza_approved = 0",
            (game_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ══════════════════════════════════════════════════════
#  TUNGI HARAKATLAR (NIGHT ACTIONS)
# ══════════════════════════════════════════════════════

async def save_night_action(
    game_id: int, round_num: int,
    actor_id: int, target_id: int,
    action_type: str, result_data: str = ""
):
    """Tungi rol harakatini saqlash."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO night_actions "
            "(game_id, round_number, actor_id, target_id, action_type, result_data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (game_id, round_num, actor_id, target_id, action_type, result_data)
        )
        await db.commit()


async def get_night_actions(game_id: int, round_num: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM night_actions "
            "WHERE game_id = ? AND round_number = ? AND processed = 0",
            (game_id, round_num)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def mark_night_action_processed(action_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE night_actions SET processed = 1 WHERE id = ?",
            (action_id,)
        )
        await db.commit()


async def get_player_night_action(
    game_id: int, round_num: int, actor_id: int
) -> Optional[dict]:
    """O'yinchi ushbu kecha harakat qilganmi tekshirish."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM night_actions "
            "WHERE game_id = ? AND round_number = ? AND actor_id = ?",
            (game_id, round_num, actor_id)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ══════════════════════════════════════════════════════
#  DO'KON
# ══════════════════════════════════════════════════════

async def add_shop_item(
    name: str, description: str, price: int, effect_code: str
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO shop_items (name, description, price, effect_code) "
            "VALUES (?, ?, ?, ?)",
            (name, description, price, effect_code)
        )
        await db.commit()
        return cur.lastrowid


async def get_all_shop_items() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_items WHERE is_active = 1 ORDER BY price ASC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_shop_item(item_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shop_items WHERE item_id = ?", (item_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def buy_item(user_id: int, item_id: int) -> bool:
    item = await get_shop_item(item_id)
    if not item:
        return False
    user = await get_user(user_id)
    if not user or user["coins"] < item["price"]:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins - ? WHERE user_id = ?",
            (item["price"], user_id)
        )
        await db.execute(
            "INSERT INTO purchases (user_id, item_id) VALUES (?, ?)",
            (user_id, item_id)
        )
        await db.commit()
    return True


async def get_user_purchases(user_id: int, unused_only: bool = False) -> list:
    query = """
        SELECT p.id, p.bought_at, p.used, p.game_id,
               s.name, s.description, s.effect_code, s.item_id
        FROM purchases p
        JOIN shop_items s ON p.item_id = s.item_id
        WHERE p.user_id = ?
    """
    params = [user_id]
    if unused_only:
        query += " AND p.used = 0"
    query += " ORDER BY p.bought_at DESC"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def mark_item_used(purchase_id: int, game_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE purchases SET used = 1, game_id = ?, "
            "used_at = datetime('now') WHERE id = ?",
            (game_id, purchase_id)
        )
        await db.commit()


async def get_purchase_by_id(purchase_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT p.id, p.user_id, p.bought_at, p.used,
                      s.name, s.description, s.effect_code, s.item_id
               FROM purchases p
               JOIN shop_items s ON p.item_id = s.item_id
               WHERE p.id = ?""",
            (purchase_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ══════════════════════════════════════════════════════
#  ARIZA COOLDOWN
# ══════════════════════════════════════════════════════

async def check_ariza_cooldown(user_id: int, cooldown_seconds: int = 60) -> bool:
    """True qaytarsa — cooldown o'tgan, ariza yuborish mumkin."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_ariza FROM ariza_cooldown WHERE user_id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return True
    from datetime import datetime
    last = datetime.fromisoformat(row[0])
    diff = (datetime.utcnow() - last).total_seconds()
    return diff >= cooldown_seconds


async def update_ariza_cooldown(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO ariza_cooldown (user_id, last_ariza) VALUES (?, datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET last_ariza = datetime('now')",
            (user_id,)
        )
        await db.commit()


# ══════════════════════════════════════════════════════
#  KARMA (Sudyani baholash)
# ══════════════════════════════════════════════════════

async def cast_karma_vote(
    game_id: int, judge_id: int, voter_id: int, vote: int
) -> bool:
    """
    vote: +1 yoki -1
    Qaytaradi: True = muvaffaqiyatli, False = allaqachon ovoz bergan
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO karma_votes (game_id, judge_id, voter_id, vote) "
                "VALUES (?, ?, ?, ?)",
                (game_id, judge_id, voter_id, vote)
            )
            await db.commit()
        # Sudyaning karmasi va ratingiga ta'sir
        await add_coins(judge_id, 10 * vote)
        await add_rating(judge_id, 5 * vote)
        return True
    except Exception:
        return False  # UNIQUE constraint — allaqachon ovoz berilgan


async def get_karma_summary(game_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT SUM(vote) as total, COUNT(*) as count "
            "FROM karma_votes WHERE game_id = ?",
            (game_id,)
        ) as cur:
            row = await cur.fetchone()
            return {"total": row[0] or 0, "count": row[1] or 0}


# ══════════════════════════════════════════════════════
#  JAMOA MAXFIY CHAT LOGI
# ══════════════════════════════════════════════════════

async def log_team_chat(
    game_id: int, sender_id: int, team: str, message_text: str
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO team_chat_log (game_id, sender_id, team, message_text) "
            "VALUES (?, ?, ?, ?)",
            (game_id, sender_id, team, message_text)
        )
        await db.commit()


# ══════════════════════════════════════════════════════
#  G'OLIBLAR VA REYTING
# ══════════════════════════════════════════════════════

async def reward_winners(
    game_id: int, winning_team: str,
    coins: int = 200, rating_bonus: int = 50
) -> list:
    players = await get_team_players(game_id, winning_team)
    for p in players:
        await add_coins(p["user_id"], coins)
        await add_rating(p["user_id"], rating_bonus)
    return [p["user_id"] for p in players]


async def penalize_losers(
    game_id: int, losing_team: str, rating_penalty: int = 20
):
    players = await get_team_players(game_id, losing_team)
    for p in players:
        await add_rating(p["user_id"], -rating_penalty)


# ══════════════════════════════════════════════════════
#  /arz_sudya — Impechment ovozlari
# ══════════════════════════════════════════════════════

async def cast_impeachment_vote(
    game_id: int, voter_id: int
) -> int:
    """
    Ovoz beradi va umumiy ovozlar sonini qaytaradi.
    Ikki marta ovoz berish oldini olish uchun — night_actions dan foydalanamiz.
    """
    existing = await get_player_night_action(
        game_id, -1, voter_id  # -1 = impechment round
    )
    if existing:
        return -1  # allaqachon ovoz bergan
    await save_night_action(game_id, -1, voter_id, 0, "impeachment")
    # Umumiy ovozlarni sanash
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM night_actions "
            "WHERE game_id = ? AND round_number = -1 AND action_type = 'impeachment'",
            (game_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0
