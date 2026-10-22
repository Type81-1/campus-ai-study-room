"""统计查询。

只放聚合 SQL，指标口径由 services/stats_service.py 决定。
"""
from __future__ import annotations


def counters(session, today: str) -> dict:
    total = session.query_one("SELECT COUNT(*) AS total FROM reservations")["total"]
    today_count = session.query_one(
        "SELECT COUNT(*) AS total FROM reservations WHERE reservation_date=?", (today,)
    )["total"]
    checked_in = session.query_one(
        "SELECT COUNT(*) AS total FROM reservations WHERE status='checked_in'"
    )["total"]
    cancelled = session.query_one(
        "SELECT COUNT(*) AS total FROM reservations WHERE status='cancelled'"
    )["total"]
    expired = session.query_one(
        "SELECT COUNT(*) AS total FROM reservations WHERE status='expired'"
    )["total"]
    open_violations = session.query_one(
        "SELECT COUNT(*) AS total FROM violations WHERE status='open'"
    )["total"]
    return {
        "total": int(total),
        "today": int(today_count),
        "checked_in": int(checked_in),
        "cancelled": int(cancelled),
        "expired": int(expired),
        "open_violations": int(open_violations),
    }


def popular_seats(session, limit: int = 5) -> list[dict]:
    return session.query_all(
        "SELECT s.code, COUNT(*) AS count FROM reservations r JOIN seats s ON s.id = r.seat_id "
        "WHERE r.status != 'cancelled' GROUP BY s.id, s.code ORDER BY count DESC, s.id LIMIT ?",
        (limit,),
    )


def daily_trend(session, limit: int = 7) -> list[dict]:
    return session.query_all(
        "SELECT reservation_date AS day, COUNT(*) AS count FROM reservations "
        "GROUP BY reservation_date ORDER BY reservation_date DESC LIMIT ?",
        (limit,),
    )


def slot_distribution(session) -> list[dict]:
    """按时段统计预约热度，用于说明「哪些时段紧张」。"""
    return session.query_all(
        "SELECT start_time, COUNT(*) AS count FROM reservations "
        "WHERE status != 'cancelled' GROUP BY start_time ORDER BY start_time"
    )


def floor_usage(session) -> list[dict]:
    return session.query_all(
        "SELECT s.floor, COUNT(*) AS count FROM reservations r JOIN seats s ON s.id = r.seat_id "
        "WHERE r.status != 'cancelled' GROUP BY s.floor ORDER BY s.floor"
    )
