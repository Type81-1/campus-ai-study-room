"""单元测试：时段规则（纯函数，不访问数据库）。"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from tests import base  # noqa: F401  （负责 sys.path 与测试环境变量）

from backend.errors import ValidationError
from backend.services.slot_rules import overlaps, parse_slot

NOW = datetime(2026, 5, 10, 9, 0)


class SlotRulesTest(unittest.TestCase):
    def test_accepts_valid_slot(self):
        slot = parse_slot("2026-05-11", "09:00", "11:30", now=NOW)
        self.assertEqual(slot.day_text, "2026-05-11")
        self.assertEqual(slot.start_text, "09:00")
        self.assertEqual(slot.end_text, "11:30")
        self.assertEqual(slot.duration_minutes, 150)

    def test_same_day_is_allowed(self):
        slot = parse_slot("2026-05-10", "10:00", "12:00", now=NOW)
        self.assertEqual(slot.day_text, "2026-05-10")

    def test_rejects_past_date(self):
        with self.assertRaises(ValidationError):
            parse_slot("2026-05-09", "09:00", "11:00", now=NOW)

    def test_rejects_reversed_range(self):
        with self.assertRaises(ValidationError):
            parse_slot("2026-05-11", "11:00", "09:00", now=NOW)

    def test_rejects_zero_length(self):
        with self.assertRaises(ValidationError):
            parse_slot("2026-05-11", "09:00", "09:00", now=NOW)

    def test_rejects_over_four_hours(self):
        with self.assertRaises(ValidationError):
            parse_slot("2026-05-11", "09:00", "13:30", now=NOW)

    def test_accepts_exactly_four_hours(self):
        slot = parse_slot("2026-05-11", "09:00", "13:00", now=NOW)
        self.assertEqual(slot.duration_minutes, 240)

    def test_rejects_non_half_hour(self):
        for start, end in (("09:10", "11:00"), ("09:00", "11:20")):
            with self.subTest(start=start, end=end), self.assertRaises(ValidationError):
                parse_slot("2026-05-11", start, end, now=NOW)

    def test_rejects_bad_format(self):
        for day, start, end in (
            ("2026/05/11", "09:00", "11:00"),
            ("2026-05-11", "9点", "11:00"),
            ("", "09:00", "11:00"),
        ):
            with self.subTest(day=day, start=start, end=end), self.assertRaises(ValidationError):
                parse_slot(day, start, end, now=NOW)

    def test_overlaps(self):
        d = date(2026, 5, 11)
        a = datetime.combine(d, datetime.min.time()).replace(hour=9)
        b = a + timedelta(hours=2)
        self.assertTrue(overlaps(a, b, a + timedelta(hours=1), b + timedelta(hours=1)))
        self.assertTrue(overlaps(a, b, a - timedelta(hours=1), a + timedelta(minutes=30)))
        # 首尾相接不算冲突（半开区间）
        self.assertFalse(overlaps(a, b, b, b + timedelta(hours=2)))
        self.assertFalse(overlaps(a, b, a - timedelta(hours=2), a))


if __name__ == "__main__":
    unittest.main(verbosity=2)
