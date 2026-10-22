"""预约表读写。"""
from __future__ import annotations

from datetime import datetime

ACTIVE_STATUSES = ("booked", "checked_in")


def find_overlap(session, seat_id, day: str, start: str, end: str, exclude_id=None) -> dict | None:
    """同一座位、同一日期、时段有交集且仍有效 → 冲突。"""
    sql = (
        "SELECT id FROM reservations "
        "WHERE seat_id=? AND reservation_date=? AND status IN ('booked','checked_in') "
        "AND start_time < ? AND end_time > ?"
    )
    params = [seat_id, day, end, start]
    if exclude_id:
        sql += " AND id != ?"
        params.append(exclude_id)
    return session.query_one(sql, params)


def create(session, user_id, seat_id, day: str, start: str, end: str) -> int:
    return session.insert(
        "INSERT INTO reservations (user_id, seat_id, reservation_date, start_time, end_time) "
        "VALUES (?,?,?,?,?)",
        (user_id, seat_id, day, start, end),
    )


def get(session, reservation_id) -> dict | None:
    return session.query_one("SELECT * FROM reservations WHERE id=?", (reservation_id,))


DETAIL_SQL = (
    "SELECT r.*, s.code AS seat_code, s.floor, s.zone, s.near_window, s.power, "
    "       u.name AS user_name, u.username "
    "FROM reservations r "
    "JOIN seats s ON s.id = r.seat_id "
    "JOIN users u ON u.id = r.user_id "
)


def get_detail(session, reservation_id) -> dict | None:
    return session.query_one(DETAIL_SQL + "WHERE r.id=?", (reservation_id,))


def list_by_user(session, user_id) -> list[dict]:
    return session.query_all(
        "SELECT r.*, s.code AS seat_code, s.floor, s.zone "
        "FROM reservations r JOIN seats s ON s.id = r.seat_id "
        "WHERE r.user_id=? ORDER BY r.reservation_date DESC, r.start_time DESC",
        (user_id,),
    )


def set_status(session, reservation_id, status: str, mark_checkin: bool = False) -> None:
    if mark_checkin:
        # 显式传本地时间，避免 SQLite 的 CURRENT_TIMESTAMP 取 UTC 与业务时间不一致
        session.execute(
            "UPDATE reservations SET status=?, checkin_at=? WHERE id=?",
            (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reservation_id),
        )
    else:
        session.execute("UPDATE reservations SET status=? WHERE id=?", (status, reservation_id))


def list_sweepable(session, latest_day: str) -> list[dict]:
    """待扫描：仍在进行中且日期不晚于今天的预约（含座位编号，便于生成提示语）。"""
    return session.query_all(
        "SELECT r.id, r.user_id, r.seat_id, r.reservation_date, r.start_time, r.end_time, "
        "       r.status, s.code AS seat_code "
        "FROM reservations r JOIN seats s ON s.id = r.seat_id "
        "WHERE r.status IN ('booked','checked_in') AND r.reservation_date <= ? "
        "ORDER BY r.reservation_date, r.start_time",
        (latest_day,),
    )


def count_active_same_slot(session, user_id, day: str, start: str, end: str) -> int:
    row = session.query_one(
        "SELECT COUNT(*) AS total FROM reservations "
        "WHERE user_id=? AND reservation_date=? AND status IN ('booked','checked_in') "
        "AND start_time < ? AND end_time > ?",
        (user_id, day, end, start),
    )
    return int(row["total"]) if row else 0


def busy_seat_ids(session, day: str, start: str, end: str) -> set[int]:
    """一次查出该时段全部被占用的座位 id，避免按座位逐条查询（N+1）。"""
    rows = session.query_all(
        "SELECT DISTINCT seat_id FROM reservations "
        "WHERE reservation_date=? AND status IN ('booked','checked_in') "
        "AND start_time < ? AND end_time > ?",
        (day, end, start),
    )
    return {int(row["seat_id"]) for row in rows}

