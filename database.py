import os
import aiosqlite
from datetime import date, datetime


async def init_db(db_path: str):
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS polls (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    TEXT    NOT NULL,
                channel_id  TEXT    NOT NULL,
                message_id  TEXT,
                title       TEXT    NOT NULL,
                creator_id  TEXT    NOT NULL,
                start_date  TEXT    NOT NULL,
                days        INTEGER NOT NULL DEFAULT 10,
                created_at  TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS votes (
                poll_id     INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
                user_id     TEXT    NOT NULL,
                username    TEXT    NOT NULL,
                day_index   INTEGER NOT NULL,
                slot_index  INTEGER NOT NULL,
                status      INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (poll_id, user_id, day_index, slot_index)
            );
        """)
        await db.commit()


async def create_poll(
    db_path: str,
    guild_id: str,
    channel_id: str,
    title: str,
    creator_id: str,
    start_date: date,
    days: int = 10,
) -> int:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "INSERT INTO polls (guild_id, channel_id, title, creator_id, start_date, days, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, title, creator_id, start_date.isoformat(), days, datetime.now().isoformat()),
        )
        await db.commit()
        return cursor.lastrowid


async def set_poll_message_id(db_path: str, poll_id: int, message_id: str):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE polls SET message_id = ? WHERE id = ?", (message_id, poll_id))
        await db.commit()


async def get_poll(db_path: str, poll_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM polls WHERE id = ?", (poll_id,)) as c:
            row = await c.fetchone()
            return dict(row) if row else None


async def delete_poll(db_path: str, poll_id: int):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM polls WHERE id = ?", (poll_id,))
        await db.commit()


async def cycle_vote(
    db_path: str,
    poll_id: int,
    user_id: str,
    username: str,
    day_index: int,
    slot_index: int,
) -> int:
    """Cycle status 0→1→2→3→0 and return new status."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            "SELECT status FROM votes WHERE poll_id=? AND user_id=? AND day_index=? AND slot_index=?",
            (poll_id, user_id, day_index, slot_index),
        ) as c:
            row = await c.fetchone()
        current = row[0] if row else 0
        new_status = (current + 1) % 4
        await db.execute(
            "INSERT INTO votes (poll_id, user_id, username, day_index, slot_index, status) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(poll_id, user_id, day_index, slot_index) "
            "DO UPDATE SET status=excluded.status, username=excluded.username",
            (poll_id, user_id, username, day_index, slot_index, new_status),
        )
        await db.commit()
        return new_status


async def get_user_votes(db_path: str, poll_id: int, user_id: str) -> dict:
    """Return {(day_index, slot_index): status}."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT day_index, slot_index, status FROM votes WHERE poll_id=? AND user_id=?",
            (poll_id, user_id),
        ) as c:
            rows = await c.fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


async def get_aggregate_counts(db_path: str, poll_id: int) -> dict:
    """Return {(day_index, slot_index): {status_int: count}}."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT day_index, slot_index, status, COUNT(*) "
            "FROM votes WHERE poll_id=? AND status > 0 "
            "GROUP BY day_index, slot_index, status",
            (poll_id,),
        ) as c:
            rows = await c.fetchall()
    counts: dict = {}
    for day_i, slot_i, status, count in rows:
        key = (day_i, slot_i)
        counts.setdefault(key, {})[status] = count
    return counts


async def get_respondents(db_path: str, poll_id: int) -> list[dict]:
    """Return unique voters who have at least one status > 0."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT DISTINCT user_id, username FROM votes WHERE poll_id=? AND status > 0",
            (poll_id,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]
