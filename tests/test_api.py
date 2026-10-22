"""集成测试：覆盖登录、座位查询、预约冲突、签到核销、权限、违规扫描等主流程。

用例直接调用 Api.handle（与 HTTP 层等价），不依赖端口占用，便于 CI 反复执行。
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, time

from tests.base import ApiTestCase, future_day, today_text


class HealthAndAuthTest(ApiTestCase):
    def test_health(self):
        status, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("database", body)
        self.assertIn(body["database"]["backend"], ("sqlite", "mysql"))

    def test_login_success_does_not_leak_password(self):
        status, body = self.post("/api/login", {"username": "student001", "password": "123456"})
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["role"], "student")
        self.assertNotIn("password", body["user"])

    def test_login_wrong_password(self):
        status, body = self.post("/api/login", {"username": "student001", "password": "bad"})
        self.assertEqual(status, 401)
        self.assertFalse(body["ok"])

    def test_login_missing_field(self):
        status, _ = self.post("/api/login", {"username": "student001"})
        self.assertEqual(status, 400)

    def test_unknown_api(self):
        status, _ = self.get("/api/nope")
        self.assertEqual(status, 404)


class SeatQueryTest(ApiTestCase):
    def test_seats_list(self):
        status, body = self.get(
            "/api/seats",
            {"date": [future_day()], "start": ["09:00"], "end": ["11:00"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(body["seats"]), 24)
        self.assertTrue(all(seat["available"] for seat in body["seats"]))

    def test_seat_becomes_unavailable_after_booking(self):
        day = future_day()
        self.book(1, 1, day)
        status, body = self.get("/api/seats", {"date": [day], "start": ["09:00"], "end": ["11:00"]})
        target = next(seat for seat in body["seats"] if seat["id"] == 1)
        self.assertFalse(target["available"])
        self.assertEqual(target["status_label"], "已占用")

    def test_partial_overlap_is_busy(self):
        day = future_day()
        self.book(1, 2, day, "09:00", "11:00")
        status, body = self.get("/api/seats", {"date": [day], "start": ["10:00"], "end": ["12:00"]})
        target = next(seat for seat in body["seats"] if seat["id"] == 2)
        self.assertFalse(target["available"])

    def test_adjacent_slot_is_free(self):
        day = future_day()
        self.book(1, 3, day, "09:00", "11:00")
        status, body = self.get("/api/seats", {"date": [day], "start": ["11:00"], "end": ["13:00"]})
        target = next(seat for seat in body["seats"] if seat["id"] == 3)
        self.assertTrue(target["available"])

    def test_maintenance_seat_cannot_be_booked(self):
        with self.db.session(write=True) as session:
            session.execute("UPDATE seats SET status='maintenance' WHERE id=4")
        status, body = self.get(
            "/api/seats", {"date": [future_day()], "start": ["09:00"], "end": ["11:00"]}
        )
        target = next(seat for seat in body["seats"] if seat["id"] == 4)
        self.assertFalse(target["available"])
        self.assertEqual(target["status_label"], "维护中")
        status, _ = self.book(1, 4, future_day())
        self.assertEqual(status, 409)


class ReservationFlowTest(ApiTestCase):
    def test_create_reservation(self):
        day = future_day()
        status, body = self.book(1, 1, day)
        self.assertEqual(status, 201)
        self.assertEqual(body["reservation"]["seat_code"], "1F-01")
        self.assertEqual(body["reservation"]["status"], "booked")

    def test_conflict_on_same_seat(self):
        day = future_day()
        self.book(1, 1, day)
        status, body = self.book(2, 1, day)
        self.assertEqual(status, 409)
        self.assertIn("已被预约", body["message"])

    def test_same_user_cannot_double_book_same_slot(self):
        day = future_day()
        self.book(1, 1, day)
        status, body = self.book(1, 2, day)
        self.assertEqual(status, 409)
        self.assertIn("该时段已有其他预约", body["message"])

    def test_create_requires_all_fields(self):
        status, body = self.post("/api/reservations", {"user_id": 1})
        self.assertEqual(status, 400)
        self.assertIn("缺少字段", body["message"])

    def test_create_rejects_unknown_seat(self):
        status, _ = self.book(1, 9999, future_day())
        self.assertEqual(status, 404)

    def test_create_rejects_unknown_user(self):
        status, _ = self.book(9999, 1, future_day())
        self.assertEqual(status, 401)

    def test_create_rejects_bad_slot(self):
        status, _ = self.book(1, 1, future_day(), "09:10", "11:00")   # 非整点/半点
        self.assertEqual(status, 400)
        status, _ = self.book(1, 2, future_day(), "09:00", "14:00")   # 超过 4 小时
        self.assertEqual(status, 400)
        status, _ = self.book(1, 3, "2020-01-01")                     # 过去的日期
        self.assertEqual(status, 400)

    def test_cancel(self):
        day = future_day()
        _, body = self.book(1, 1, day)
        reservation_id = body["reservation"]["id"]
        status, _ = self.call("DELETE", f"/api/reservations/{reservation_id}", {"user_id": ["1"]})
        self.assertEqual(status, 200)
        # 取消后座位释放
        status, seats = self.get(
            "/api/seats", {"date": [day], "start": ["09:00"], "end": ["11:00"]}
        )
        target = next(seat for seat in seats["seats"] if seat["id"] == 1)
        self.assertTrue(target["available"])

    def test_cancel_others_reservation_forbidden(self):
        _, body = self.book(1, 1)
        reservation_id = body["reservation"]["id"]
        status, _ = self.call("DELETE", f"/api/reservations/{reservation_id}", {"user_id": ["2"]})
        self.assertEqual(status, 403)

    def test_cancel_unknown_reservation(self):
        status, _ = self.call("DELETE", "/api/reservations/9999", {"user_id": ["1"]})
        self.assertEqual(status, 404)

    def test_admin_can_cancel_any_reservation(self):
        _, body = self.book(1, 1)
        reservation_id = body["reservation"]["id"]
        status, _ = self.call("DELETE", f"/api/reservations/{reservation_id}", {"user_id": ["3"]})
        self.assertEqual(status, 200)

    def test_checkin_and_checkout(self):
        _, body = self.book(1, 1)
        reservation_id = body["reservation"]["id"]
        status, payload = self.post(f"/api/reservations/{reservation_id}/checkin", {"user_id": 1})
        self.assertEqual(status, 200)
        self.assertEqual(payload["reservation"]["status"], "checked_in")
        self.assertIsNotNone(payload["reservation"]["checkin_at"])

        status, _ = self.post(f"/api/reservations/{reservation_id}/checkin", {"user_id": 1})
        self.assertEqual(status, 409)  # 重复签到

        status, payload = self.post(f"/api/reservations/{reservation_id}/checkout", {"user_id": 1})
        self.assertEqual(status, 200)
        self.assertEqual(payload["reservation"]["status"], "completed")

        status, _ = self.post(f"/api/reservations/{reservation_id}/checkout", {"user_id": 1})
        self.assertEqual(status, 409)

    def test_checkin_requires_owner(self):
        _, body = self.book(1, 1)
        reservation_id = body["reservation"]["id"]
        status, _ = self.post(f"/api/reservations/{reservation_id}/checkin", {"user_id": 2})
        self.assertEqual(status, 403)

    def test_cannot_cancel_after_checkin(self):
        _, body = self.book(1, 1)
        reservation_id = body["reservation"]["id"]
        self.post(f"/api/reservations/{reservation_id}/checkin", {"user_id": 1})
        status, _ = self.call("DELETE", f"/api/reservations/{reservation_id}", {"user_id": ["1"]})
        self.assertEqual(status, 409)

    def test_my_reservations(self):
        day = future_day()
        self.book(1, 1, day, "09:00", "11:00")
        self.book(1, 2, day, "13:00", "15:00")
        status, body = self.get("/api/reservations", {"user_id": ["1"]})
        self.assertEqual(status, 200)
        self.assertEqual(len(body["reservations"]), 2)
        status, _ = self.get("/api/reservations")
        self.assertEqual(status, 400)


class PermissionTest(ApiTestCase):
    def test_student_cannot_access_admin_stats(self):
        status, _ = self.get("/api/admin/stats", {"user_id": ["1"]})
        self.assertEqual(status, 403)

    def test_admin_can_access_stats(self):
        status, body = self.get("/api/admin/stats", {"user_id": ["3"]})
        self.assertEqual(status, 200)
        for key in ("total", "today", "checked_in", "open_violations", "popular", "by_day"):
            self.assertIn(key, body["stats"])

    def test_anonymous_cannot_access_admin(self):
        status, _ = self.get("/api/admin/violations", {"user_id": ["9999"]})
        self.assertEqual(status, 401)

    def test_admin_users_list(self):
        status, body = self.get("/api/admin/users", {"user_id": ["3"]})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(body["users"]), 3)
        self.assertNotIn("password", body["users"][0])


class RecommendationTest(ApiTestCase):
    def test_returns_ranked_seats(self):
        status, body = self.get(
            "/api/recommendations",
            {"user_id": ["1"], "date": [future_day()], "start": ["09:00"], "end": ["11:00"]},
        )
        self.assertEqual(status, 200)
        items = body["recommendations"]
        self.assertTrue(items)
        self.assertLessEqual(len(items), 5)
        scores = [item["score"] for item in items]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(item["reason"] for item in items))

    def test_excludes_busy_seats(self):
        day = future_day()
        self.book(1, 1, day)
        status, body = self.get(
            "/api/recommendations",
            {"user_id": ["2"], "date": [day], "start": ["09:00"], "end": ["11:00"]},
        )
        self.assertNotIn(1, [item["id"] for item in body["recommendations"]])

    def test_preference_changes_ranking(self):
        day = future_day()
        status, body = self.get(
            "/api/recommendations",
            {"user_id": ["1"], "date": [day], "start": ["09:00"], "end": ["11:00"]},
        )
        # student001 偏好靠窗 + 电源，首位应当同时命中两项
        top = body["recommendations"][0]
        self.assertEqual(top["near_window"], 1)
        self.assertEqual(top["power"], 1)


class ViolationScanTest(ApiTestCase):
    def _book_early_slot(self, user_id: int, seat_id: int, start="00:00", end="02:00"):
        status, body = self.book(user_id, seat_id, today_text(), start, end)
        self.assertEqual(status, 201, body)
        return body["reservation"]

    def test_no_show_creates_violation(self):
        reservation = self._book_early_slot(1, 1)
        summary = self.api.violations.scan(now=datetime.combine(date.today(), time(12, 0)))
        self.assertEqual(summary["expired"], 1)
        self.assertEqual(summary["violations"], 1)

        status, body = self.get("/api/reservations", {"user_id": ["1"]})
        self.assertEqual(body["reservations"][0]["status"], "expired")

        status, body = self.get("/api/admin/violations", {"user_id": ["3"]})
        self.assertEqual(len(body["violations"]), 1)
        self.assertEqual(body["violations"][0]["kind"], "no_show")
        self.assertEqual(body["violations"][0]["reservation_id"], reservation["id"])

    def test_overstay_creates_violation(self):
        reservation = self._book_early_slot(1, 2)
        self.post(f"/api/reservations/{reservation['id']}/checkin", {"user_id": 1})
        summary = self.api.violations.scan(
            now=datetime.combine(datetime.now().date(), time(3, 0))
        )
        self.assertEqual(summary["overstay"], 1)
        status, body = self.get("/api/reservations", {"user_id": ["1"]})
        self.assertEqual(body["reservations"][0]["status"], "completed")
        status, body = self.get("/api/admin/violations", {"user_id": ["3"]})
        self.assertEqual(body["violations"][0]["kind"], "overstay")

    def test_scan_is_idempotent(self):
        self._book_early_slot(1, 3)
        moment = datetime.combine(datetime.now().date(), time(12, 0))
        self.api.violations.scan(now=moment)
        second = self.api.violations.scan(now=moment)
        self.assertEqual(second["violations"], 0)
        status, body = self.get("/api/admin/violations", {"user_id": ["3"]})
        self.assertEqual(len(body["violations"]), 1)

    def test_scan_ignores_future_reservations(self):
        status, _ = self.book(1, 5, future_day())
        self.assertEqual(status, 201)
        summary = self.api.violations.scan(now=datetime.now())
        self.assertEqual(summary["expired"], 0)
        self.assertEqual(summary["overstay"], 0)

    def test_violation_blocks_booking_until_resolved(self):
        # 三个互不重叠的时段，避免「同用户同时段」校验先触发
        slots = [("00:00", "02:00"), ("02:00", "04:00"), ("04:00", "06:00")]
        for index, (start, end) in enumerate(slots):
            self._book_early_slot(1, index + 1, start, end)
        self.api.violations.scan(now=datetime.combine(datetime.now().date(), time(12, 0)))

        status, body = self.post(
            "/api/reservations",
            {
                "user_id": 1,
                "seat_id": 10,
                "reservation_date": future_day(),
                "start_time": "09:00",
                "end_time": "11:00",
            },
        )
        self.assertEqual(status, 409)
        self.assertIn("违规记录", body["message"])

        status, body = self.get("/api/admin/violations", {"user_id": ["3"]})
        for violation in body["violations"]:
            status, _ = self.post(
                f"/api/admin/violations/{violation['id']}/resolve", {"user_id": 3}
            )
            self.assertEqual(status, 200)

        status, _ = self.post(
            "/api/reservations",
            {
                "user_id": 1,
                "seat_id": 10,
                "reservation_date": future_day(),
                "start_time": "09:00",
                "end_time": "11:00",
            },
        )
        self.assertEqual(status, 201)

    def test_resolve_requires_admin(self):
        self._book_early_slot(1, 6)
        self.api.violations.scan(now=datetime.combine(datetime.now().date(), time(12, 0)))
        status, body = self.get("/api/admin/violations", {"user_id": ["3"]})
        violation_id = body["violations"][0]["id"]
        status, _ = self.post(f"/api/admin/violations/{violation_id}/resolve", {"user_id": 1})
        self.assertEqual(status, 403)
        status, _ = self.post(f"/api/admin/violations/{violation_id}/resolve", {"user_id": 3})
        self.assertEqual(status, 200)
        status, _ = self.post(f"/api/admin/violations/{violation_id}/resolve", {"user_id": 3})
        self.assertEqual(status, 404)  # 已处理

    def test_manual_scan_endpoint(self):
        status, body = self.post("/api/admin/violations/scan", {"user_id": 3})
        self.assertEqual(status, 200)
        self.assertIn("summary", body)
        status, _ = self.post("/api/admin/violations/scan", {"user_id": 1})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
