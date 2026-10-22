"""用户表读写。"""
from __future__ import annotations

PUBLIC_COLUMNS = "id, username, name, role, preferences, created_at"


def get_by_id(session, user_id) -> dict | None:
    return session.query_one(f"SELECT {PUBLIC_COLUMNS} FROM users WHERE id=?", (user_id,))


def get_with_secret(session, user_id) -> dict | None:
    return session.query_one("SELECT * FROM users WHERE id=?", (user_id,))


def find_by_credentials(session, username: str, password: str) -> dict | None:
    return session.query_one(
        f"SELECT {PUBLIC_COLUMNS} FROM users WHERE username=? AND password=?",
        (username, password),
    )


def list_all(session) -> list[dict]:
    return session.query_all(f"SELECT {PUBLIC_COLUMNS} FROM users ORDER BY id")
