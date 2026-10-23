"""集成测试：覆盖鉴权、座位查询、预约冲突、签到核销、权限、违规扫描、后台管理。

用例直接调用 Api.handle（与 HTTP 层等价），不依赖端口占用，便于反复执行。
身份一律通过令牌传递，接口不再接受 user_id 参数。
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, time

from tests.base import DEMO_PASSWORD, ApiTestCase, future_day, today_text


class HealthAndAuthTest(ApiTestCase):
    def test_health_is_public(self):
        status, body = self.get("/api/health", token=None)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn(body["database"]["backend"], ("sqlite", "mysql"))

    def test_login_returns_token_and_hides_password(self):
        status, body = self.post(
            "/api/login", {"username": "student001", "password": DEMO_PASSWORD}, token=None
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["token"])
        self.assertIn("expires_at", body)
        self.assertEqual(body["user"]["role"], "student")
        self.assertNotIn("password", body["user"])

    def test_password_is_stored_as_hash(self):
        with self.db.session() as session:
            row = session.query_one("SELECT password FROM users WHERE username='student001'")
        self.assertTrue(row["password"].startswith("pbkdf2_sha256$"))
        self.assertNotEqual(row["password"], DEMO_PASSWORD)

    def test_login_wrong_password(self):
        status, body = self.post(
            "/api/login", {"username": "student001", "password": "bad"}, token=None
        )
        self.assertEqual(status, 401)
        self.assertFalse(body["ok"])

    def test_login_missing_field(self):
        status, _ = self.post("/api/login", {"username": "student001"}, token=None)
        self.assertEqual(status, 400)

    def test_protected_api_requires_token(self):
        for path in ("/api/seats", "/api/reservations", "/api/recommendations"):
            with self.subTest(path=path):
                status, body = self.get(path, token=None)
                self.assertEqual(status, 401)
                self.assertIn("登录", body["message"])

    def test_invalid_token_rejected(self):
        status, _ = self.get("/api/seats", token="not-a-real-token")
        self.assertEqual(status, 401)

    def test_me_returns_current_user(self):
        status, body = self.get("/api/me")
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["username"], "student001")

    def test_logout_invalidates_token(self):
        status, _ = self.post("/api/logout", {}, token=self.tokens["student001"])
        self.assertEqual(status, 200)
        status, _ = self.get("/api/me", token=self.tokens["student001"])
        self.assertEqual(status, 401)

    def test_unknown_api_with_token(self):
        status, _ = self.get("/api/nope")
        self.assertEqual(status, 404)


class SeatQueryTest(ApiTestCase):
    def test_seats_list(self):
        status, body = self.get(
            "/api/seats", {"date": [future_day()], "start": ["09:00"], "end": ["11:00"]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(body["seats"]), 24)
        self.assertTrue(all(seat["available"] for seat in body["seats"]))

    def test_seat_becomes_unavailable_after_booking(self):
        day = future_day()
        self.book(1, day)
        status, body = self.get("/api/seats", {"date": [day], "start": ["09:00"], "end": ["11:00"]})
        target = next(seat for seat in body["seats"] if seat["id"] == 1)
        self.assertFalse(target["available"])
        self.assertEqual(target["status_label"], "已占用")

    def test_partial_overlap_is_busy(self):
        day = future_day()
        self.book(2, day, "09:00", "11:00")
        status, body = self.get("/api/seats", {"date": [day], "start": ["10:00"], "end": ["12:00"]})
        target = next(seat for seat in body["seats"] if seat["id"] == 2)
        self.assertFalse(target["available"])

    def test_adjacent_slot_is_free(self):
        day = future_day()
        self.book(3, day, "09:00", "11:00")
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
        status, _ = self.book(4, future_day())
        self.assertEqual(status, 409)


class ReservationFlowTest(ApiTestCase):
    def test_create_reservation(self):
        day = future_day()
        status, body = self.book(1, day)
        self.assertEqual(status, 201)
        self.assertEqual(body["reservation"]["seat_code"], "1F-01")
        self.assertEqual(body["reservation"]["status"], "booked")
        self.assertEqual(body["reservation"]["user_id"], 1)

    def test_conflict_on_same_seat(self):
        day = future_day()
        self.book(1, day)
        status, body = self.book(1, day, token=self.tokens["student002"])
        self.assertEqual(status, 409)
        self.assertIn("已被预约", body["message"])

    def test_same_user_cannot_double_book_same_slot(self):
        day = future_day()
        self.book(1, day)
        status, body = self.book(2, day)
        self.assertEqual(status, 409)
        self.assertIn("该时段已有其他预约", body["message"])

    def test_create_requires_all_fields(self):
        status, body = self.post("/api/reservations", {"start_time": "09:00"})
        self.assertEqual(status, 400)
        self.assertIn("缺少字段", body["message"])

    def test_create_rejects_unknown_seat(self):
        status, _ = self.book(9999, future_day())
        self.assertEqual(status, 404)

    def test_create_rejects_bad_slot(self):
        status, _ = self.book(1, future_day(), "09:10", "11:00")   # 非整点/半点
        self.assertEqual(status, 400)
        status, _ = self.book(2, future_day(), "09:00", "14:00")   # 超过 4 小时
        self.assertEqual(status, 400)
        status, _ = self.book(3, "2020-01-01")                     # 过去的日期
        self.assertEqual(status, 400)

    def test_cancel(self):
        day = future_day()
        _, body = self.book(1, day)
        reservation_id = body["reservation"]["id"]
        status, _ = self.call("DELETE", f"/api/reservations/{reservation_id}")
        self.assertEqual(status, 200)
        status, seats = self.get("/api/seats", {"date": [day], "start": ["09:00"], "end": ["11:00"]})
        target = next(seat for seat in seats["seats"] if seat["id"] == 1)
        self.assertTrue(target["available"])

    def test_cancel_others_reservation_forbidden(self):
        _, body = self.book(1)
        reservation_id = body["reservation"]["id"]
        status, _ = self.call(
            "DELETE", f"/api/reservations/{reservation_id}", token=self.tokens["student002"]
        )
        self.assertEqual(status, 403)

    def test_cancel_unknown_reservation(self):
        status, _ = self.call("DELETE", "/api/reservations/9999")
        self.assertEqual(status, 404)

    def test_admin_can_cancel_any_reservation(self):
        _, body = self.book(1)
        reservation_id = body["reservation"]["id"]
        status, _ = self.call(
            "DELETE", f"/api/reservations/{reservation_id}", token=self.tokens["admin"]
        )
        self.assertEqual(status, 200)

    def test_checkin_and_checkout(self):
        _, body = self.book(1)
        reservation_id = body["reservation"]["id"]
        status, payload = self.post(f"/api/reservations/{reservation_id}/checkin", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["reservation"]["status"], "checked_in")
        self.assertIsNotNone(payload["reservation"]["checkin_at"])

        status, _ = self.post(f"/api/reservations/{reservation_id}/checkin", {})
        self.assertEqual(status, 409)  # 重复签到

        status, payload = self.post(f"/api/reservations/{reservation_id}/checkout", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["reservation"]["status"], "completed")

        status, _ = self.post(f"/api/reservations/{reservation_id}/checkout", {})
        self.assertEqual(status, 409)

    def test_checkin_requires_owner(self):
        _, body = self.book(1)
        reservation_id = body["reservation"]["id"]
        status, _ = self.post(
            f"/api/reservations/{reservation_id}/checkin", {}, token=self.tokens["student002"]
        )
        self.assertEqual(status, 403)

    def test_cannot_cancel_after_checkin(self):
        _, body = self.book(1)
        reservation_id = body["reservation"]["id"]
        self.post(f"/api/reservations/{reservation_id}/checkin", {})
        status, _ = self.call("DELETE", f"/api/reservations/{reservation_id}")
        self.assertEqual(status, 409)

    def test_my_reservations_only_returns_own(self):
        day = future_day()
        self.book(1, day, "09:00", "11:00")
        self.book(2, day, "13:00", "15:00", token=self.tokens["student002"])
        status, body = self.get("/api/reservations")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["reservations"]), 1)
        self.assertEqual(body["reservations"][0]["user_id"], 1)

    def test_user_id_param_cannot_be_used_to_peek_others(self):
        """P1 修复的核心回归：伪造 user_id 不再能查看他人预约。"""
        self.book(1, future_day(), "09:00", "11:00", token=self.tokens["student002"])
        status, body = self.get("/api/reservations", {"user_id": ["2"]})
        self.assertEqual(status, 200)
        self.assertEqual(body["reservations"], [])


class PermissionTest(ApiTestCase):
    def test_student_cannot_access_admin_stats(self):
        status, _ = self.get("/api/admin/stats")
        self.assertEqual(status, 403)

    def test_admin_can_access_stats(self):
        status, body = self.get("/api/admin/stats", token=self.tokens["admin"])
        self.assertEqual(status, 200)
        for key in ("total", "today", "checked_in", "open_violations", "popular", "by_day"):
            self.assertIn(key, body["stats"])

    def test_admin_subpaths_require_admin(self):
        for path in ("/api/admin/violations", "/api/admin/users", "/api/admin/seats"):
            with self.subTest(path=path):
                status, _ = self.get(path)
                self.assertEqual(status, 403)

    def test_user_id_param_cannot_elevate(self):
        """伪造管理员 user_id 不再能进入管理接口。"""
        status, _ = self.get("/api/admin/stats", {"user_id": ["3"]})
        self.assertEqual(status, 403)


class RecommendationTest(ApiTestCase):
    def test_returns_ranked_seats(self):
        status, body = self.get(
            "/api/recommendations", {"date": [future_day()], "start": ["09:00"], "end": ["11:00"]}
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
        self.book(1, day)
        status, body = self.get(
            "/api/recommendations",
            {"date": [day], "start": ["09:00"], "end": ["11:00"]},
            token=self.tokens["student002"],
        )
        self.assertNotIn(1, [item["id"] for item in body["recommendations"]])

    def test_preference_changes_ranking(self):
        status, body = self.get(
            "/api/recommendations", {"date": [future_day()], "start": ["09:00"], "end": ["11:00"]}
        )
        top = body["recommendations"][0]
        self.assertEqual(top["near_window"], 1)
        self.assertEqual(top["power"], 1)


class ViolationScanTest(ApiTestCase):
    def _book_early_slot(self, seat_id: int, start="00:00", end="02:00", token=None):
        status, body = self.book(seat_id, today_text(), start, end, token=token or self.tokens["student001"])
        self.assertEqual(status, 201, body)
        return body["reservation"]

    def test_no_show_creates_violation(self):
        reservation = self._book_early_slot(1)
        summary = self.api.violations.scan(now=datetime.combine(date.today(), time(12, 0)))
        self.assertEqual(summary["expired"], 1)
        self.assertEqual(summary["violations"], 1)

        status, body = self.get("/api/reservations")
        self.assertEqual(body["reservations"][0]["status"], "expired")

        status, body = self.get("/api/admin/violations", token=self.tokens["admin"])
        self.assertEqual(len(body["violations"]), 1)
        self.assertEqual(body["violations"][0]["kind"], "no_show")
        self.assertEqual(body["violations"][0]["reservation_id"], reservation["id"])

    def test_overstay_creates_violation(self):
        reservation = self._book_early_slot(2)
        self.post(f"/api/reservations/{reservation['id']}/checkin", {})
        summary = self.api.violations.scan(now=datetime.combine(date.today(), time(3, 0)))
        self.assertEqual(summary["overstay"], 1)
        status, body = self.get("/api/reservations")
        self.assertEqual(body["reservations"][0]["status"], "completed")
        status, body = self.get("/api/admin/violations", token=self.tokens["admin"])
        self.assertEqual(body["violations"][0]["kind"], "overstay")

    def test_scan_is_idempotent(self):
        self._book_early_slot(3)
        moment = datetime.combine(date.today(), time(12, 0))
        self.api.violations.scan(now=moment)
        second = self.api.violations.scan(now=moment)
        self.assertEqual(second["violations"], 0)
        status, body = self.get("/api/admin/violations", token=self.tokens["admin"])
        self.assertEqual(len(body["violations"]), 1)

    def test_scan_ignores_future_reservations(self):
        status, _ = self.book(5, future_day())
        self.assertEqual(status, 201)
        summary = self.api.violations.scan(now=datetime.now())
        self.assertEqual(summary["expired"], 0)
        self.assertEqual(summary["overstay"], 0)

    def test_violation_blocks_booking_until_resolved(self):
        slots = [("00:00", "02:00"), ("02:00", "04:00"), ("04:00", "06:00")]
        for index, (start, end) in enumerate(slots):
            self._book_early_slot(index + 1, start, end)
        self.api.violations.scan(now=datetime.combine(date.today(), time(12, 0)))

        status, body = self.book(10, future_day())
        self.assertEqual(status, 409)
        self.assertIn("违规记录", body["message"])

        status, body = self.get("/api/admin/violations", token=self.tokens["admin"])
        for violation in body["violations"]:
            status, _ = self.post(
                f"/api/admin/violations/{violation['id']}/resolve", {}, token=self.tokens["admin"]
            )
            self.assertEqual(status, 200)

        status, _ = self.book(10, future_day())
        self.assertEqual(status, 201)

    def test_resolve_requires_admin(self):
        self._book_early_slot(6)
        self.api.violations.scan(now=datetime.combine(date.today(), time(12, 0)))
        status, body = self.get("/api/admin/violations", token=self.tokens["admin"])
        violation_id = body["violations"][0]["id"]
        status, _ = self.post(f"/api/admin/violations/{violation_id}/resolve", {})
        self.assertEqual(status, 403)
        status, _ = self.post(
            f"/api/admin/violations/{violation_id}/resolve", {}, token=self.tokens["admin"]
        )
        self.assertEqual(status, 200)
        status, _ = self.post(
            f"/api/admin/violations/{violation_id}/resolve", {}, token=self.tokens["admin"]
        )
        self.assertEqual(status, 404)  # 已处理

    def test_manual_scan_endpoint(self):
        status, body = self.post("/api/admin/violations/scan", {}, token=self.tokens["admin"])
        self.assertEqual(status, 200)
        self.assertIn("summary", body)
        status, _ = self.post("/api/admin/violations/scan", {})
        self.assertEqual(status, 403)


class CheckinWindowTest(ApiTestCase):
    """打开签到窗口校验后的行为。"""

    checkin_enforced = True

    def test_too_early_checkin_is_rejected(self):
        # 明天的时段一定早于「开始前 30 分钟」
        status, body = self.book(1, future_day(), "09:00", "11:00")
        self.assertEqual(status, 201)
        reservation_id = body["reservation"]["id"]
        status, payload = self.post(f"/api/reservations/{reservation_id}/checkin", {})
        self.assertEqual(status, 409)
        self.assertIn("还未到签到时间", payload["message"])

    def test_late_checkin_expires_reservation(self):
        now = datetime.now()
        if now.time() < time(0, 30):
            self.skipTest("临近零点，今天的 00:00 时段不构成迟到")
        _, body = self.book(2, today_text(), "00:00", "02:00")
        reservation_id = body["reservation"]["id"]
        status, payload = self.post(f"/api/reservations/{reservation_id}/checkin", {})
        self.assertEqual(status, 409)
        self.assertIn("已超过签到截止时间", payload["message"])

        status, body = self.get("/api/reservations")
        self.assertEqual(body["reservations"][0]["status"], "expired")

        status, body = self.get("/api/admin/violations", token=self.tokens["admin"])
        self.assertEqual(len(body["violations"]), 1)
        self.assertEqual(body["violations"][0]["kind"], "no_show")

    def test_checkin_inside_window(self):
        day = future_day()
        _, body = self.book(3, day, "09:00", "11:00")
        reservation_id = body["reservation"]["id"]
        # 直接注入时间，避免依赖真实时钟
        moment = datetime.combine(date.fromisoformat(day), time(9, 5))
        result = self.api.reservations.checkin(reservation_id, self.actor(), now=moment)
        self.assertEqual(result["reservation"]["status"], "checked_in")


class AdminManageTest(ApiTestCase):
    def test_list_seats(self):
        status, body = self.get("/api/admin/seats", token=self.tokens["admin"])
        self.assertEqual(status, 200)
        self.assertEqual(len(body["seats"]), 24)

    def test_toggle_seat_status(self):
        status, body = self.post(
            "/api/admin/seats/5/status", {"status": "maintenance"}, token=self.tokens["admin"]
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["seat"]["status"], "maintenance")

        status, _ = self.book(5, future_day())
        self.assertEqual(status, 409)

        status, _ = self.post(
            "/api/admin/seats/5/status", {"status": "available"}, token=self.tokens["admin"]
        )
        self.assertEqual(status, 200)
        status, _ = self.book(5, future_day())
        self.assertEqual(status, 201)

    def test_invalid_seat_status(self):
        status, body = self.post(
            "/api/admin/seats/5/status", {"status": "broken"}, token=self.tokens["admin"]
        )
        self.assertEqual(status, 400)

    def test_unknown_seat(self):
        status, _ = self.post(
            "/api/admin/seats/9999/status", {"status": "maintenance"}, token=self.tokens["admin"]
        )
        self.assertEqual(status, 404)

    def test_seat_status_requires_admin(self):
        status, _ = self.post("/api/admin/seats/5/status", {"status": "maintenance"})
        self.assertEqual(status, 403)

    def test_user_list_with_stats(self):
        self.book(1, future_day())
        status, body = self.get("/api/admin/users", token=self.tokens["admin"])
        self.assertEqual(status, 200)
        first = next(user for user in body["users"] if user["username"] == "student001")
        self.assertEqual(first["reservation_count"], 1)
        self.assertIn("open_violations", first)
        self.assertNotIn("password", first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
