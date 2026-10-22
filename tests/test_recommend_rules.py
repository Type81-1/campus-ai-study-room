"""单元测试：推荐评分规则（纯函数）。"""
from __future__ import annotations

import unittest

from tests import base  # noqa: F401

from backend.services.recommendation_service import (
    BASE_SCORE,
    POWER_BONUS,
    QUIET_BONUS,
    WINDOW_BONUS,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
