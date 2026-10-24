"""智能推荐模块：基于可解释规则的轻量推荐（v2）。

评分因子（全部可解释、可单测）：

| 因子 | 分值 | 说明 |
| --- | --- | --- |
| 基础分 | 50 | 保证任何空闲座位都有基础分 |
| 靠窗偏好命中 | +25 | 用户 preferences.window 为真且座位靠窗 |
| 电源偏好命中 | +20 | 用户 preferences.power 为真且座位有电源 |
| 安静区 | +5 | 区域属性加分 |
| 冷门座位 | +5 | 该座位近 7 天预约次数不高于人均，分散热门座位压力 |
| 前后时段空闲 | +5 | 目标时段前后各 1 小时也空闲，适合连续学习 |

另外统计「时段热度」（该时段已占用座位占比），用于提示该时段是否紧张，
但不直接改分——热度是全局信息，不该让所有座位一起涨跌。

同分按座位编号升序，结果稳定可复现。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from ..repositories import reservation_repository as repo
from ..repositories import seat_repository, user_repository
from .slot_rules import parse_slot

BASE_SCORE = 50
WINDOW_BONUS = 25
POWER_BONUS = 20
QUIET_BONUS = 5
COLD_BONUS = 5
CONTINUITY_BONUS = 5

HISTORY_DAYS = 7
HEAT_EASY = 0.35        # 低于此占用率视作空闲
HEAT_BUSY = 0.75        # 高于此占用率提示接近满座


def heat_label(ratio: float) -> str:
    if ratio < HEAT_EASY:
        return "空闲"
    if ratio < 0.6:
        return "较松"
    if ratio < HEAT_BUSY:
        return "较紧张"
    return "接近满座"


def heat_advice(ratio: float) -> str:
    if ratio < HEAT_EASY:
        return "该时段座位充足，可以慢慢挑"
    if ratio < 0.6:
        return "该时段还有余量，建议按偏好选择"
    if ratio < HEAT_BUSY:
        return "该时段较紧张，建议尽快预约或换相邻时段"
    return "该时段接近满座，可尝试相邻时段或其他楼层"


def _shift_clock(clock: str, minutes: int) -> str | None:
    """在 HH:MM 上做加减；跨天（越界）时返回 None，表示该侧无需检查。"""
    try:
        base = datetime.strptime(clock, "%H:%M") + timedelta(minutes=minutes)
    except ValueError:
        return None
    if base.date() != datetime(1900, 1, 1).date():
        return None
    return base.strftime("%H:%M")


def score_seat(seat: dict, preferences: dict, context: dict | None = None) -> tuple[int, list[str]]:
    """给单个座位打分，返回 (分数, 可解释理由列表)。"""
    ctx = context or {}
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

    recent = ctx.get("recent_count")
    average = ctx.get("recent_average")
    # 历史数据太少时不做冷热区分，避免所有座位都白拿 5 分
    if recent is not None and average is not None and average >= 1 and recent <= average:
        score += COLD_BONUS
        reasons.append("近期较少被预约，更容易约到")

    if ctx.get("adjacent_free"):
        score += CONTINUITY_BONUS
        reasons.append("前后时段同样空闲")

    return score, reasons


class RecommendationService:
    def __init__(self, db, cfg=None) -> None:
        self.db = db
        self.cfg = cfg

    def recommend(self, user_id, day: str, start: str, end: str, limit: int = 5) -> dict:
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

            before_start = _shift_clock(slot.start_text, -60)
            after_end = _shift_clock(slot.end_text, 60)
            busy_before = (
                repo.busy_seat_ids(session, slot.day_text, before_start, slot.start_text)
                if before_start
                else set()
            )
            busy_after = (
                repo.busy_seat_ids(session, slot.day_text, slot.end_text, after_end)
                if after_end
                else set()
            )
            since = (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()
            recent_counts = repo.seat_recent_counts(session, since)

        total = max(len(seats), 1)
        recent_average = sum(recent_counts.values()) / total
        ratio = len(busy) / total

        candidates = []
        for seat in seats:
            if seat["status"] != "available" or int(seat["id"]) in busy:
                continue
            seat_id = int(seat["id"])
            context = {
                "recent_count": recent_counts.get(seat_id, 0),
                "recent_average": recent_average,
                "adjacent_free": seat_id not in busy_before and seat_id not in busy_after,
            }
            score, reasons = score_seat(seat, preferences, context)
            candidates.append(
                {
                    **seat,
                    "score": score,
                    "reason": "、".join(reasons) or "当前时段空闲",
                }
            )

        candidates.sort(key=lambda item: (-item["score"], item["id"]))
        return {
            "items": candidates[:limit],
            "context": {
                "date": slot.day_text,
                "start": slot.start_text,
                "end": slot.end_text,
                "total_seats": len(seats),
                "busy_seats": len(busy),
                "available_seats": max(len(seats) - len(busy), 0),
                "slot_heat": round(ratio * 100, 1),
                "heat_label": heat_label(ratio),
                "advice": heat_advice(ratio),
            },
        }
