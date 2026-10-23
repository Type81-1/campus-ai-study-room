"""智能推荐模块：基于可解释规则的轻量推荐。

评分规则（可解释、可单测）：
- 基础分 50；
- 命中「靠窗」偏好 +25，命中「电源」偏好 +20；
- 安静区 +5（默认加分项）。
分数相同按座位编号先后排序，保证结果稳定可复现。
"""
from __future__ import annotations

import json

from ..repositories import reservation_repository as repo
from ..repositories import seat_repository, user_repository
from .slot_rules import parse_slot

BASE_SCORE = 50
WINDOW_BONUS = 25
POWER_BONUS = 20
QUIET_BONUS = 5


def score_seat(seat: dict, preferences: dict) -> tuple[int, list[str]]:
    score = BASE_SCORE
    reasons: list[str] = []
    if preferences.get("window") and int(seat.get("near_window") or 0):
        score += WINDOW_BONUS
        reasons.append("符合靠窗偏好")
    if preferences.get("power") and int(seat.get("power") or 0):
        score += POWER_BONUS
        reasons.append("提供电源")
    if seat.get("zone") == "安静区":
        score += QUIET_BONUS
        reasons.append("安静区")
    return score, reasons


class RecommendationService:
    def __init__(self, db, cfg=None) -> None:
        self.db = db
        self.cfg = cfg

    def recommend(self, user_id, day: str, start: str, end: str, limit: int = 5) -> list[dict]:
        slot = parse_slot(day, start, end)
        preferences: dict = {}
        with self.db.session() as session:
            if user_id not in (None, ""):
                user = user_repository.get_by_id(session, user_id)
                if user and user.get("preferences"):
                    try:
                        preferences = json.loads(user["preferences"])
                    except (TypeError, ValueError):
                        preferences = {}
            seats = seat_repository.list_all(session)
            busy = repo.busy_seat_ids(session, slot.day_text, slot.start_text, slot.end_text)

        candidates = []
        for seat in seats:
            if seat["status"] != "available" or int(seat["id"]) in busy:
                continue
            score, reasons = score_seat(seat, preferences)
            candidates.append(
                {
                    **seat,
                    "score": score,
                    "reason": "、".join(reasons) or "当前时段空闲",
                }
            )
        candidates.sort(key=lambda item: (-item["score"], item["id"]))
        return candidates[:limit]
