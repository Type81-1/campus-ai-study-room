"""违规记录表读写。"""
from __future__ import annotations


def create(session, user_id, reservation_id, kind: str, message: str) -> int:
    return session.insert(
        "INSERT INTO violations (user_id, reservation_id, kind, message) VALUES (?,?,?,?)",
        (user_id, reservation_id, kind, message),
    )


def get(session, violation_id) -> dict | None:
    return session.query_one("SELECT * FROM violations WHERE id=?", (violation_id,))


def list_all(session) -> list[dict]:
    return session.query_all(
        "SELECT v.*, u.name AS user_name, u.username, s.code AS seat_code, "
        "       r.reservation_date, r.start_time, r.end_time "
        "FROM violations v "
        "JOIN users u ON u.id = v.user_id "
        "LEFT JOIN reservations r ON r.id = v.reservation_id "
        "LEFT JOIN seats s ON s.id = r.seat_id "
        "ORDER BY v.created_at DESC, v.id DESC"
    )


def resolve(session, violation_id) -> int:
    return session.execute(
        "UPDATE violations SET status='resolved' WHERE id=? AND status='open'", (violation_id,)
    ).rowcount


def count_open_since(session, user_id, since: str) -> int:
    row = session.query_one(
        "SELECT COUNT(*) AS total FROM violations "
        "WHERE user_id=? AND status='open' AND created_at >= ?",
        (user_id, since),
    )
    return int(row["total"]) if row else 0


def exists_for_reservation(session, reservation_id, kind: str) -> bool:
    row = session.query_one(
        "SELECT id FROM violations WHERE reservation_id=? AND kind=?", (reservation_id, kind)
    )
    return row is not None
