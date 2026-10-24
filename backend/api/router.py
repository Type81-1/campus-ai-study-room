"""HTTP 路由表。

每个分支只做三件事：取参数 → 调 service → 组装 JSON，不写任何 SQL 或业务判断。
身份统一由 `Authorization: Bearer <token>` 解析成 `actor`，接口不再接受 user_id 参数。
"""
from __future__ import annotations

import re
from datetime import datetime

from ..config import config
from ..db import Database
from ..errors import NotFound, ValidationError
from ..events import bus
from ..services import auth_service
from ..services.admin_service import AdminService
from ..services.recommendation_service import RecommendationService
from ..services.reservation_service import ReservationService
from ..services.stats_service import StatsService
from ..services.violation_service import ViolationService


def _q(query: dict, name: str, default=None):
    values = query.get(name)
    return values[0] if values else default


class Api:
    def __init__(self, db: Database, cfg=config) -> None:
        self.db = db
        self.cfg = cfg
        self.violations = ViolationService(db, cfg)
        self.reservations = ReservationService(db, cfg, self.violations)
        self.recommendations = RecommendationService(db, cfg)
        self.stats = StatsService(db)
        self.admin = AdminService(db)

    def authenticate(self, token: str | None) -> dict:
        """供 SSE 等非标准入口复用令牌校验。"""
        return auth_service.authenticate(self.db, token, self.cfg)

    # ------------------------------------------------------------------ 分发
    def handle(self, method: str, path: str, query: dict, payload: dict, token: str | None = None):
        if method == "GET" and path == "/api/health":
            return self._health()
        if method == "POST" and path == "/api/login":
            return 200, {"ok": True, **auth_service.login(self.db, payload.get("username"), payload.get("password"), self.cfg)}

        # 其余接口一律要求有效令牌
        actor = auth_service.authenticate(self.db, token, self.cfg)

        if method == "POST" and path == "/api/logout":
            return 200, {"ok": True, "message": auth_service.logout(self.db, token)}
        if method == "GET" and path == "/api/me":
            return 200, {"ok": True, "user": actor}

        if method == "GET":
            return self._get(path, query, actor)
        if method == "POST":
            return self._post(path, payload, actor)
        if method == "DELETE":
            return self._delete(path, query, actor)
        raise NotFound("接口不存在")

    # ------------------------------------------------------------------ GET
    def _health(self):
        return 200, {
            "ok": True,
            "service": "study-room",
            "version": "2.2",
            "time": datetime.now().isoformat(timespec="seconds"),
            "database": self.cfg.describe(),
        }

    def _get(self, path: str, query: dict, actor: dict):
        if path == "/api/seats":
            seats = self.reservations.list_seats(
                _q(query, "date", datetime.now().date().isoformat()),
                _q(query, "start", "09:00"),
                _q(query, "end", "11:00"),
            )
            return 200, {"ok": True, "seats": seats}

        if path == "/api/reservations":
            return 200, {"ok": True, "reservations": self.reservations.list_mine(actor)}

        if path == "/api/recommendations":
            result = self.recommendations.recommend(
                actor["id"],
                _q(query, "date", datetime.now().date().isoformat()),
                _q(query, "start", "09:00"),
                _q(query, "end", "11:00"),
            )
            return 200, {
                "ok": True,
                "recommendations": result["items"],
                "context": result["context"],
            }

        if path == "/api/admin/stats":
            auth_service.require_admin(actor)
            return 200, {"ok": True, "stats": self.stats.overview()}

        if path == "/api/admin/violations":
            auth_service.require_admin(actor)
            return 200, {"ok": True, "violations": self.violations.list_all()}

        if path == "/api/admin/users":
            auth_service.require_admin(actor)
            return 200, {"ok": True, "users": self.admin.list_users()}

        if path == "/api/admin/seats":
            auth_service.require_admin(actor)
            return 200, {"ok": True, "seats": self.admin.list_seats()}

        raise NotFound("接口不存在")

    # ------------------------------------------------------------------ POST
    def _post(self, path: str, payload: dict, actor: dict):
        if path == "/api/reservations":
            missing = [
                field
                for field in ("seat_id", "reservation_date", "start_time", "end_time")
                if payload.get(field) in (None, "")
            ]
            if missing:
                raise ValidationError("缺少字段：" + "、".join(missing))
            reservation = self.reservations.create(
                actor,
                payload["seat_id"],
                payload["reservation_date"],
                payload["start_time"],
                payload["end_time"],
            )
            bus.publish("reservation.created", {
                "seat_id": reservation["seat_id"],
                "date": reservation["reservation_date"],
                "start": reservation["start_time"],
                "end": reservation["end_time"],
            })
            return 201, {"ok": True, "message": "预约成功", "reservation": reservation}

        match = re.fullmatch(r"/api/reservations/(\d+)/checkin", path)
        if match:
            result = self.reservations.checkin(int(match.group(1)), actor)
            bus.publish("reservation.checked_in", {"reservation_id": int(match.group(1))})
            return 200, {"ok": True, **result}

        match = re.fullmatch(r"/api/reservations/(\d+)/checkout", path)
        if match:
            result = self.reservations.checkout(int(match.group(1)), actor)
            bus.publish("reservation.checked_out", {"reservation_id": int(match.group(1))})
            return 200, {"ok": True, **result}

        match = re.fullmatch(r"/api/admin/seats/(\d+)/status", path)
        if match:
            auth_service.require_admin(actor)
            seat = self.admin.set_seat_status(int(match.group(1)), payload.get("status"))
            bus.publish("seat.status", {"seat_id": seat["id"], "status": seat["status"]})
            return 200, {"ok": True, "message": "座位状态已更新", "seat": seat}

        match = re.fullmatch(r"/api/admin/violations/(\d+)/resolve", path)
        if match:
            auth_service.require_admin(actor)
            message = self.violations.resolve(int(match.group(1)))
            bus.publish("violation.resolved", {"violation_id": int(match.group(1))})
            return 200, {"ok": True, "message": message}

        # 演示 / 巡检用：手动触发一次违规扫描
        if path == "/api/admin/violations/scan":
            auth_service.require_admin(actor)
            summary = self.violations.scan()
            bus.publish("violation.scanned", {"summary": summary})
            return 200, {"ok": True, "message": "扫描完成", "summary": summary}

        raise NotFound("接口不存在")

    # ------------------------------------------------------------------ DELETE
    def _delete(self, path: str, query: dict, actor: dict):
        match = re.fullmatch(r"/api/reservations/(\d+)", path)
        if not match:
            raise NotFound("接口不存在")
        message = self.reservations.cancel(int(match.group(1)), actor)
        bus.publish("reservation.cancelled", {"reservation_id": int(match.group(1))})
        return 200, {"ok": True, "message": message}
