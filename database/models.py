import aiosqlite
import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None or _db._conn is None:
        _db = await aiosqlite.connect(DB_PATH)
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA busy_timeout=5000")
    return _db


@asynccontextmanager
async def db_connection() -> AsyncIterator[aiosqlite.Connection]:
    db = await get_db()
    try:
        yield db
    except Exception:
        await db.rollback()
        raise


async def init_db():
    async with db_connection() as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_url TEXT,
                video_title TEXT,
                quality TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )
        await db.commit()
        logger.info("Database initialized")


async def add_user(user_id: int, username: str = None, first_name: str = None):
    async with db_connection() as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            """,
            (user_id, username, first_name),
        )
        await db.commit()


async def add_history(user_id: int, url: str, title: str, quality: str):
    async with db_connection() as db:
        await db.execute(
            """
            INSERT INTO download_history (user_id, video_url, video_title, quality)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, url, title, quality),
        )
        await db.commit()


async def close_db():
    global _db
    if _db is not None:
        try:
            await _db.close()
        except Exception:
            pass
        _db = None
