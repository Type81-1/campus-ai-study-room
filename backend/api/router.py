"""HTTP 路由表。

每个分支只做三件事：取参数 → 调 service → 组装 JSON，不写任何 SQL 或业务判断。
"""
from __future__ import annotations

import re
from datetime import datetime

from ..config import config
from ..db import Database
from ..errors import NotFound, ValidationError
from ..services import auth_service
from ..services.recommendation_service import RecommendationService
from ..services.reservation_service import ReservationService
from ..services.stats_service import StatsService
from ..services.violation_service import ViolationService


def _q(query: dict, name: str, default=None):
    values = query.get(name)
    return values[0] if values else default


class Api:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.reservations = ReservationService(db)
        self.recommendations = RecommendationService(db)
        self.violations = ViolationService(db)
        self.stats = StatsService(db)

    # ------------------------------------------------------------------ 分发
    def handle(self, method: str, path: str, query: dict, payload: dict) -> tuple[int, dict]:
        if method == "GET":
            return self._get(path, query)
        if method == "POST":
            return self._post(path, payload)
        if method == "DELETE":
            return self._delete(path, query)
        raise NotFound("接口不存在")

    # ------------------------------------------------------------------ GET
    def _get(self, path: str, query: dict) -> tuple[int, dict]:
        if path == "/api/health":
            return 200, {
                "ok": True,
                "service": "study-room",
                "time": datetime.now().isoformat(timespec="seconds"),
                "database": config.describe(),
            }

        if path == "/api/seats":
            seats = self.reservations.list_seats(
                _q(query, "date", datetime.now().date().isoformat()),
                _q(query, "start", "09:00"),
                _q(query, "end", "11:00"),
            )
            return 200, {"ok": True, "seats": seats}

        if path == "/api/reservations":
            user_id = _q(query, "user_id")
            if not user_id:
                raise ValidationError("需要 user_id")
            return 200, {"ok": True, "reservations": self.reservations.list_mine(user_id)}

        if path == "/api/recommendations":
            items = self.recommendations.recommend(
                _q(query, "user_id"),
                _q(query, "date", datetime.now().date().isoformat()),
                _q(query, "start", "09:00"),
                _q(query, "end", "11:00"),
            )
            return 200, {"ok": True, "recommendations": items}

        if path == "/api/admin/stats":
            with self.db.session() as session:
                auth_service.require_admin(session, _q(query, "user_id"))
            return 200, {"ok": True, "stats": self.stats.overview()}

        if path == "/api/admin/violations":
            with self.db.session() as session:
                auth_service.require_admin(session, _q(query, "user_id"))
            return 200, {"ok": True, "violations": self.violations.list_all()}

        if path == "/api/admin/users":
            with self.db.session() as session:
                auth_service.require_admin(session, _q(query, "user_id"))
                users = auth_service.list_users(session)
            return 200, {"ok": True, "users": users}

        raise NotFound("接口不存在")

    # ------------------------------------------------------------------ POST
    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        if path == "/api/login":
            user = auth_service.login(self.db, payload.get("username"), payload.get("password"))
            return 200, {"ok": True, "user": user}

        if path == "/api/reservations":
            missing = [
                field
                for field in ("user_id", "seat_id", "reservation_date", "start_time", "end_time")
                if payload.get(field) in (None, "")
            ]
            if missing:
                raise ValidationError("缺少字段：" + "、".join(missing))
            reservation = self.reservations.create(
                payload["user_id"],
                payload["seat_id"],
                payload["reservation_date"],
                payload["start_time"],
                payload["end_time"],
            )
            return 201, {"ok": True, "message": "预约成功", "reservation": reservation}

        match = re.fullmatch(r"/api/reservations/(\d+)/checkin", path)
        if match:
            result = self.reservations.checkin(int(match.group(1)), payload.get("user_id"))
            return 200, {"ok": True, **result}

        match = re.fullmatch(r"/api/reservations/(\d+)/checkout", path)
        if match:
            result = self.reservations.checkout(int(match.group(1)), payload.get("user_id"))
            return 200, {"ok": True, **result}

        match = re.fullmatch(r"/api/admin/violations/(\d+)/resolve", path)
        if match:
            with self.db.session() as session:
                auth_service.require_admin(session, payload.get("user_id"))
            return 200, {"ok": True, "message": self.violations.resolve(int(match.group(1)))}

        # 演示 / 巡检用：手动触发一次违规扫描，便于验收时现场演示
        if path == "/api/admin/violations/scan":
            with self.db.session() as session:
                auth_service.require_admin(session, payload.get("user_id"))
            summary = self.violations.scan()
            return 200, {"ok": True, "message": "扫描完成", "summary": summary}

        raise NotFound("接口不存在")

    # ------------------------------------------------------------------ DELETE
    def _delete(self, path: str, query: dict) -> tuple[int, dict]:
        match = re.fullmatch(r"/api/reservations/(\d+)", path)
        if not match:
            raise NotFound("接口不存在")
        message = self.reservations.cancel(int(match.group(1)), _q(query, "user_id"))
        return 200, {"ok": True, "message": message}
