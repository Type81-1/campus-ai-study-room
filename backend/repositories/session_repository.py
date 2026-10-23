"""会话表读写（令牌只存摘要）。"""
from __future__ import annotations


def create(session, user_id, digest: str, expires_at: str) -> int:
    return session.insert(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?,?,?)",
        (digest, user_id, expires_at),
    )


def find_user_by_token(session, digest: str, now_text: str) -> dict | None:
    return session.query_one(
        "SELECT u.id, u.username, u.name, u.role, u.preferences, u.created_at, "
        "       s.expires_at, s.id AS session_id "
        "FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash=? AND s.expires_at > ?",
        (digest, now_text),
    )


def delete(session, digest: str) -> int:
    return session.execute("DELETE FROM sessions WHERE token_hash=?", (digest,)).rowcount


def delete_for_user(session, user_id) -> int:
    return session.execute("DELETE FROM sessions WHERE user_id=?", (user_id,)).rowcount


def purge_expired(session, now_text: str) -> int:
    return session.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_text,)).rowcount
