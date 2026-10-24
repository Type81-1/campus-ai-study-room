"""单元测试：推荐评分规则（纯函数）。"""
from __future__ import annotations

import unittest

from tests import base  # noqa: F401

from backend.services.recommendation_service import (
    BASE_SCORE,
    COLD_BONUS,
    CONTINUITY_BONUS,
    POWER_BONUS,
    QUIET_BONUS,
    WINDOW_BONUS,
    heat_advice,
    heat_label,
    score_seat,
)

WINDOW_SEAT = {"id": 1, "near_window": 1, "power": 1, "zone": "靠窗区"}
INNER_SEAT = {"id": 5, "near_window": 0, "power": 1, "zone": "安静区"}
PLAIN_SEAT = {"id": 7, "near_window": 0, "power": 0, "zone": "普通区"}


class ScoreSeatTest(unittest.TestCase):
    def test_base_score_without_preferences(self):
        score, reasons = score_seat(PLAIN_SEAT, {})
        self.assertEqual(score, BASE_SCORE)
        self.assertEqual(reasons, [])

    def test_window_preference_hit(self):
        # 靠窗区不在安静区，只有靠窗加分
        score, reasons = score_seat(WINDOW_SEAT, {"window": True})
        self.assertEqual(score, BASE_SCORE + WINDOW_BONUS)
        self.assertIn("符合靠窗偏好", reasons)

    def test_window_preference_miss(self):
        score, reasons = score_seat(INNER_SEAT, {"window": True})
        self.assertEqual(score, BASE_SCORE + QUIET_BONUS)
        self.assertNotIn("符合靠窗偏好", reasons)

    def test_power_preference(self):
        score, reasons = score_seat(INNER_SEAT, {"power": True})
        self.assertEqual(score, BASE_SCORE + POWER_BONUS + QUIET_BONUS)
        self.assertIn("提供电源", reasons)

    def test_both_preferences(self):
        score, reasons = score_seat(WINDOW_SEAT, {"window": True, "power": True})
        self.assertEqual(score, BASE_SCORE + WINDOW_BONUS + POWER_BONUS)
        self.assertEqual(len(reasons), 2)

    def test_quiet_zone_bonus_is_explained(self):
        _, reasons = score_seat(INNER_SEAT, {})
        self.assertIn("安静区", reasons)


class ContextFactorTest(unittest.TestCase):
    """v2 新增的两个因子：冷门座位、前后时段连续性。"""

    def test_cold_seat_bonus(self):
        score, reasons = score_seat(PLAIN_SEAT, {}, {"recent_count": 1, "recent_average": 3.5})
        self.assertEqual(score, BASE_SCORE + COLD_BONUS)
        self.assertIn("更容易约到", "".join(reasons))

    def test_hot_seat_gets_no_bonus(self):
        score, reasons = score_seat(PLAIN_SEAT, {}, {"recent_count": 9, "recent_average": 3.5})
        self.assertEqual(score, BASE_SCORE)
        self.assertEqual(reasons, [])

    def test_equal_to_average_counts_as_cold(self):
        score, _ = score_seat(PLAIN_SEAT, {}, {"recent_count": 3, "recent_average": 3})
        self.assertEqual(score, BASE_SCORE + COLD_BONUS)

    def test_too_little_history_no_bonus(self):
        score, reasons = score_seat(PLAIN_SEAT, {}, {"recent_count": 0, "recent_average": 0.2})
        self.assertEqual(score, BASE_SCORE)
        self.assertEqual(reasons, [])

    def test_missing_context_keeps_old_behaviour(self):
        score, reasons = score_seat(PLAIN_SEAT, {}, None)
        self.assertEqual(score, BASE_SCORE)
        self.assertEqual(reasons, [])

    def test_adjacent_free_bonus(self):
        score, reasons = score_seat(PLAIN_SEAT, {}, {"adjacent_free": True})
        self.assertEqual(score, BASE_SCORE + CONTINUITY_BONUS)
        self.assertIn("前后时段同样空闲", reasons)

    def test_adjacent_busy_no_bonus(self):
        score, reasons = score_seat(PLAIN_SEAT, {}, {"adjacent_free": False})
        self.assertEqual(score, BASE_SCORE)
        self.assertEqual(reasons, [])

    def test_all_factors_stack(self):
        score, reasons = score_seat(
            WINDOW_SEAT,
            {"window": True, "power": True},
            {"recent_count": 0, "recent_average": 2, "adjacent_free": True},
        )
        self.assertEqual(
            score,
            BASE_SCORE + WINDOW_BONUS + POWER_BONUS + COLD_BONUS + CONTINUITY_BONUS,
        )
        self.assertEqual(len(reasons), 4)


class HeatTest(unittest.TestCase):
    def test_labels(self):
        for ratio, expected in ((0.1, "空闲"), (0.5, "较松"), (0.7, "较紧张"), (0.9, "接近满座")):
            with self.subTest(ratio=ratio):
                self.assertEqual(heat_label(ratio), expected)

    def test_advice_mentions_action(self):
        self.assertIn("充足", heat_advice(0.1))
        self.assertIn("余量", heat_advice(0.5))
        self.assertIn("尽快", heat_advice(0.7))
        self.assertIn("满座", heat_advice(0.95))


if __name__ == "__main__":
    unittest.main(verbosity=2)
