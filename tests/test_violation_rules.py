"""单元测试：违规判定规则（纯函数）。"""
from __future__ import annotations

import unittest
from datetime import datetime

from tests import base  # noqa: F401

from backend.services.violation_service import (
    KIND_NO_SHOW,
    KIND_OVERSTAY,
    build_message,
    decide,
)

NO_SHOW_GRACE = 15
OVERSTAY_GRACE = 30

RESERVATION = {
    "id": 7,
    "user_id": 1,
    "seat_id": 3,
    "seat_code": "1F-03",
    "reservation_date": "2026-05-11",
    "start_time": "09:00",
    "end_time": "11:00",
    "status": "booked",
}


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 11, hour, minute)


class DecideTest(unittest.TestCase):
    def test_before_start_is_not_violation(self):
        self.assertIsNone(decide(RESERVATION, at(8, 30), NO_SHOW_GRACE, OVERSTAY_GRACE))

    def test_within_no_show_grace_is_not_violation(self):
        self.assertIsNone(decide(RESERVATION, at(9, 14), NO_SHOW_GRACE, OVERSTAY_GRACE))

    def test_no_show_at_grace_boundary(self):
        verdict = decide(RESERVATION, at(9, 15), NO_SHOW_GRACE, OVERSTAY_GRACE)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.kind, KIND_NO_SHOW)
        self.assertEqual(verdict.next_status, "expired")

    def test_no_show_late_minutes(self):
        verdict = decide(RESERVATION, at(9, 45), NO_SHOW_GRACE, OVERSTAY_GRACE)
        self.assertEqual(verdict.late_minutes, 45)

    def test_no_show_when_slot_already_ended(self):
        verdict = decide(RESERVATION, at(13, 0), NO_SHOW_GRACE, OVERSTAY_GRACE)
        self.assertEqual(verdict.kind, KIND_NO_SHOW)

    def test_checked_in_within_slot_is_fine(self):
        row = {**RESERVATION, "status": "checked_in"}
        self.assertIsNone(decide(row, at(10, 30), NO_SHOW_GRACE, OVERSTAY_GRACE))

    def test_checked_in_within_overstay_grace_is_fine(self):
        row = {**RESERVATION, "status": "checked_in"}
        self.assertIsNone(decide(row, at(11, 29), NO_SHOW_GRACE, OVERSTAY_GRACE))

    def test_overstay_at_grace_boundary(self):
        row = {**RESERVATION, "status": "checked_in"}
        verdict = decide(row, at(11, 30), NO_SHOW_GRACE, OVERSTAY_GRACE)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.late_minutes, 30)

    def test_overstay_after_grace(self):
        row = {**RESERVATION, "status": "checked_in"}
        verdict = decide(row, at(11, 31), NO_SHOW_GRACE, OVERSTAY_GRACE)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.kind, KIND_OVERSTAY)
        self.assertEqual(verdict.next_status, "completed")
        self.assertEqual(verdict.late_minutes, 31)

    def test_finished_reservation_is_ignored(self):
        for status in ("completed", "cancelled", "expired"):
            with self.subTest(status=status):
                row = {**RESERVATION, "status": status}
                self.assertIsNone(decide(row, at(23, 0), NO_SHOW_GRACE, OVERSTAY_GRACE))


class MessageTest(unittest.TestCase):
    def test_no_show_message(self):
        message = build_message(KIND_NO_SHOW, RESERVATION, 45, NO_SHOW_GRACE)
        self.assertIn("1F-03", message)
        self.assertIn("未签到", message)
        self.assertIn("45", message)

    def test_overstay_message(self):
        message = build_message(KIND_OVERSTAY, RESERVATION, 31, OVERSTAY_GRACE)
        self.assertIn("1F-03", message)
        self.assertIn("未办理结束", message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
