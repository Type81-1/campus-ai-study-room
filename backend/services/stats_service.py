"""数据统计模块：为后台看板提供聚合指标。"""
from __future__ import annotations

from datetime import date

from ..repositories import stats_repository


class StatsService:
    def __init__(self, db) -> None:
        self.db = db

    def overview(self) -> dict:
        today = date.today().isoformat()
        with self.db.session() as session:
            counters = stats_repository.counters(session, today)
            popular = stats_repository.popular_seats(session, 5)
            by_day = stats_repository.daily_trend(session, 7)
            slots = stats_repository.slot_distribution(session)
            floors = stats_repository.floor_usage(session)

        total = counters["total"] or 1
        return {
            **counters,
            "popular": popular,
            "by_day": by_day,
            "by_slot": slots,
            "by_floor": floors,
            "cancel_rate": round(counters["cancelled"] / total * 100, 1),
            "violation_rate": round(counters["expired"] / total * 100, 1),
        }
