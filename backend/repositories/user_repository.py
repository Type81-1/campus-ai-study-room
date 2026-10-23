"""用户表读写。"""
from __future__ import annotations

PUBLIC_COLUMNS = "id, username, name, role, preferences, created_at"


def get_by_id(session, user_id) -> dict | None:
    return session.query_one(f"SELECT {PUBLIC_COLUMNS} FROM users WHERE id=?", (user_id,))


def get_with_secret(session, user_id) -> dict | None:
    return session.query_one("SELECT * FROM users WHERE id=?", (user_id,))


def get_by_username_with_secret(session, username: str) -> dict | None:
    """登录用：带口令字段，由服务层做哈希校验。"""
    return session.query_one("SELECT * FROM users WHERE username=?", (username,))


def update_password(session, user_id, hashed: str) -> None:
    session.execute("UPDATE users SET password=? WHERE id=?", (hashed, user_id))


def find_by_credentials(session, username: str, password: str) -> dict | None:
    """已废弃：口令比对必须走 security.verify_password，保留仅为兼容旧调用。"""
    return session.query_one(
        f"SELECT {PUBLIC_COLUMNS} FROM users WHERE username=? AND password=?",
        (username, password),
    )


def list_all(session) -> list[dict]:
    return session.query_all(f"SELECT {PUBLIC_COLUMNS} FROM users ORDER BY id")


def list_with_stats(session) -> list[dict]:
    """用户列表 + 预约数 / 违规数，供后台管理使用。"""
    return session.query_all(
        "SELECT u.id, u.username, u.name, u.role, u.created_at, "
        "       (SELECT COUNT(*) FROM reservations r WHERE r.user_id = u.id) AS reservation_count, "
        "       (SELECT COUNT(*) FROM violations v WHERE v.user_id = u.id AND v.status='open') AS open_violations "
        "FROM users u ORDER BY u.id"
    )
