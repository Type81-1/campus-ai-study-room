"""座位表读写。"""
from __future__ import annotations


def list_all(session) -> list[dict]:
    return session.query_all("SELECT * FROM seats ORDER BY floor, id")


def get(session, seat_id) -> dict | None:
    return session.query_one("SELECT * FROM seats WHERE id=?", (seat_id,))


def lock(session, seat_id) -> dict | None:
    """对座位行加锁。

    MySQL 下是 SELECT ... FOR UPDATE（行级排他锁），SQLite 下由 BEGIN IMMEDIATE
    在库级别完成串行化。这是「并发抢同一座位」不会双订的关键。
    """
    return session.lock_row("seats", seat_id)
