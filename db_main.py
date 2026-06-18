# database/db_main.py

import aiosqlite
from typing import Optional

DB_PATH = "sud_tizimi.db"


async def create_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                coins       INTEGER DEFAULT 0,
                registered  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS games (
                game_id             INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id             INTEGER NOT NULL,
                status              TEXT DEFAULT 'waiting',
                judge_id            INTEGER,
                current_turn        TEXT DEFAULT 'white',
                round_number        INTEGER DEFAULT 1,
                voice_chat_verified INTEGER DEFAULT 0,
                -- 0=tekshirilmagan/yo'q, 1=tasdiqlangan
                created_at          TEXT DEFAULT (datetime('now')),
                finished_at         TEXT
            );
            CREATE TABLE IF NOT EXISTS players (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id         INTEGER NOT NULL REFERENCES games(game_id),
                user_id         INTEGER NOT NULL REFERENCES users(user_id),
                team            TEXT NOT NULL,
                role            TEXT,
                is_alive        INTEGER DEFAULT 1,
                muted           INTEGER DEFAULT 1,
                ariza_text      TEXT,
                ariza_approved  INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS shop_items (
                item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT,
                price       INTEGER NOT NULL,
                effect_code TEXT,
                is_active   INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS purchases (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(user_id),
                item_id     INTEGER NOT NULL REFERENCES shop_items(item_id),
                bought_at   TEXT DEFAULT (datetime('now')),
                used        INTEGER DEFAULT 0
            );
        """)
        await db.commit()


# ── USERS ─────────────────────────────────────────────
async def register_user(user_id: int, username: Optional[str], full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username, full_name = excluded.full_name
        """, (user_id, username, full_name))
        await db.commit()

async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def add_coins(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def get_coins(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


# ── GAMES ─────────────────────────────────────────────
async def create_game(chat_id: int, judge_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO games (chat_id, judge_id) VALUES (?, ?)", (chat_id, judge_id))
        await db.commit()
        return cur.lastrowid

async def get_active_game(chat_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM games WHERE chat_id = ? AND status != 'finished' ORDER BY game_id DESC LIMIT 1",
            (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def get_game_by_id(game_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM games WHERE game_id = ?", (game_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def update_game_status(game_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        if status == "finished":
            await db.execute(
                "UPDATE games SET status = ?, finished_at = datetime('now') WHERE game_id = ?",
                (status, game_id)
            )
        else:
            await db.execute("UPDATE games SET status = ? WHERE game_id = ?", (status, game_id))
        await db.commit()

async def set_current_turn(game_id: int, team: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE games SET current_turn = ? WHERE game_id = ?", (team, game_id))
        await db.commit()

async def increment_round(game_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE games SET round_number = round_number + 1 WHERE game_id = ?", (game_id,))
        await db.commit()


async def set_voice_chat_verified(game_id: int, verified: bool):
    """Video chat borligini tasdiqlash yoki bekor qilish."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE games SET voice_chat_verified = ? WHERE game_id = ?",
            (1 if verified else 0, game_id)
        )
        await db.commit()


# ── PLAYERS ───────────────────────────────────────────
async def add_player(game_id: int, user_id: int, team: str, role: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO players (game_id, user_id, team, role) VALUES (?, ?, ?, ?)",
            (game_id, user_id, team, role)
        )
        await db.commit()

async def get_players(game_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM players WHERE game_id = ?", (game_id,)) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def get_alive_players(game_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE game_id = ? AND is_alive = 1", (game_id,)
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
            "SELECT * FROM players WHERE game_id = ? AND user_id = ?", (game_id, user_id)
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
            "UPDATE players SET muted = ? WHERE game_id = ? AND team = ? AND is_alive = 1",
            (1 if muted else 0, game_id, team)
        )
        await db.commit()

async def eliminate_player(game_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET is_alive = 0, muted = 1 WHERE game_id = ? AND user_id = ?",
            (game_id, user_id)
        )
        await db.commit()

async def save_ariza(game_id: int, user_id: int, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET ariza_text = ?, ariza_approved = 0 WHERE game_id = ? AND user_id = ?",
            (text, game_id, user_id)
        )
        await db.commit()

async def approve_ariza(game_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET ariza_approved = 1 WHERE game_id = ? AND user_id = ?",
            (game_id, user_id)
        )
        await db.commit()

async def get_pending_arizalar(game_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE game_id = ? AND ariza_text IS NOT NULL AND ariza_approved = 0",
            (game_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── SHOP ──────────────────────────────────────────────
async def add_shop_item(name: str, description: str, price: int, effect_code: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO shop_items (name, description, price, effect_code) VALUES (?, ?, ?, ?)",
            (name, description, price, effect_code)
        )
        await db.commit()
        return cur.lastrowid

async def get_all_shop_items() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shop_items WHERE is_active = 1 ORDER BY price ASC") as cur:
            return [dict(r) for r in await cur.fetchall()]

async def get_shop_item(item_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shop_items WHERE item_id = ?", (item_id,)) as cur:
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
        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (item["price"], user_id))
        await db.execute("INSERT INTO purchases (user_id, item_id) VALUES (?, ?)", (user_id, item_id))
        await db.commit()
    return True

async def get_user_purchases(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT p.id, p.bought_at, p.used,
                   s.name, s.description, s.effect_code, s.item_id
            FROM purchases p JOIN shop_items s ON p.item_id = s.item_id
            WHERE p.user_id = ? ORDER BY p.bought_at DESC
        """, (user_id,)) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def mark_item_used(purchase_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE purchases SET used = 1 WHERE id = ?", (purchase_id,))
        await db.commit()


# ── G'OLIBLAR ─────────────────────────────────────────
async def reward_winners(game_id: int, winning_team: str, coins: int = 200) -> list:
    players = await get_team_players(game_id, winning_team)
    for p in players:
        await add_coins(p["user_id"], coins)
    return [p["user_id"] for p in players]