"""后台管理模块：座位状态维护、用户概览、违规处理入口。

权限统一由路由层用 `require_admin(actor)` 把关，这里只做业务校验。
"""
from __future__ import annotations

from ..errors import NotFound, ValidationError
from ..repositories import seat_repository, user_repository

SEAT_STATUSES = ("available", "maintenance")


class AdminService:
    def __init__(self, db) -> None:
        self.db = db

    # ---------- 座位 ----------
    def list_seats(self) -> list[dict]:
        with self.db.session() as session:
            return seat_repository.list_all(session)

    def set_seat_status(self, seat_id, status: str) -> dict:
        if status not in SEAT_STATUSES:
            raise ValidationError(f"座位状态只能是 {' / '.join(SEAT_STATUSES)}")
        with self.db.session(write=True) as session:
            seat = seat_repository.lock(session, seat_id)
            if not seat:
                raise NotFound("座位不存在")
            session.execute("UPDATE seats SET status=? WHERE id=?", (status, seat_id))
            seat["status"] = status
        return seat

    # ---------- 用户 ----------
    def list_users(self) -> list[dict]:
        with self.db.session() as session:
            return user_repository.list_with_stats(session)
