"""Cloudflare D1 — conversations log + forwarded messages."""
import logging
from datetime import datetime, timezone

import httpx

from config import CF_ACCOUNT_ID, D1_DATABASE_ID, D1_API_TOKEN

logger = logging.getLogger(__name__)

_BASE = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{D1_DATABASE_ID}/query"
_HEADERS = {"Authorization": f"Bearer {D1_API_TOKEN}", "Content-Type": "application/json"}

_INIT_SQL = [
    """CREATE TABLE IF NOT EXISTS conversations (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        conn_id   TEXT NOT NULL,
        user_id   INTEGER NOT NULL,
        user_name TEXT NOT NULL,
        question  TEXT NOT NULL,
        answer    TEXT NOT NULL,
        ts        TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_conv_conn ON conversations(conn_id)",
    """CREATE TABLE IF NOT EXISTS forwards (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        user_name   TEXT NOT NULL,
        msg_type    TEXT NOT NULL,
        text        TEXT,
        media_key   TEXT,
        ts          TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS muted_users (
        user_id   INTEGER PRIMARY KEY,
        user_name TEXT NOT NULL,
        muted_at  TEXT NOT NULL
    )""",
]


async def _query(sql: str, params: list | None = None) -> list[dict] | None:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(_BASE, headers=_HEADERS, json={"sql": sql, "params": params or []})
            r.raise_for_status()
            data = r.json()
            if data.get("success"):
                return data["result"][0].get("results", [])
    except Exception as exc:
        logger.error("D1 query failed: %s", exc)
    return None


async def init_db() -> None:
    for sql in _INIT_SQL:
        await _query(sql)


async def log_message(conn_id: str, user_id: int, user_name: str, question: str, answer: str) -> None:
    await _query(
        "INSERT INTO conversations (conn_id, user_id, user_name, question, answer, ts) VALUES (?, ?, ?, ?, ?, ?)",
        [conn_id, user_id, user_name, question, answer, datetime.now(timezone.utc).isoformat()],
    )


async def log_forward(user_id: int, user_name: str, msg_type: str, text: str | None, media_key: str | None) -> None:
    await _query(
        "INSERT INTO forwards (user_id, user_name, msg_type, text, media_key, ts) VALUES (?, ?, ?, ?, ?, ?)",
        [user_id, user_name, msg_type, text, media_key, datetime.now(timezone.utc).isoformat()],
    )


async def load_muted_users() -> dict[int, str]:
    rows = await _query("SELECT user_id, user_name FROM muted_users")
    if not rows:
        return {}
    return {int(row["user_id"]): row["user_name"] for row in rows}


async def save_muted_user(user_id: int, user_name: str) -> None:
    await _query(
        "INSERT OR REPLACE INTO muted_users (user_id, user_name, muted_at) VALUES (?, ?, ?)",
        [user_id, user_name, datetime.now(timezone.utc).isoformat()],
    )


async def remove_muted_user(user_id: int) -> None:
    await _query("DELETE FROM muted_users WHERE user_id = ?", [user_id])


async def load_history(conn_id: str, limit: int = 10) -> list[dict]:
    rows = await _query(
        "SELECT question, answer FROM conversations WHERE conn_id = ? ORDER BY ts DESC LIMIT ?",
        [conn_id, limit],
    )
    if not rows:
        return []
    history = []
    for row in reversed(rows):
        history.append({"role": "user", "content": row["question"]})
        history.append({"role": "assistant", "content": row["answer"]})
    return history
