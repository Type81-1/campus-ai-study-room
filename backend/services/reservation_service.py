"""预约模块：座位查询、创建预约、取消、签到核销、结束自习。

身份：所有写操作都基于已认证的 `actor`（由路由层从令牌解析），不再接受前端传的 user_id。

并发要点：创建预约在同一个写事务里「锁座位行 → 查冲突 → 插入」，
SQLite 用 BEGIN IMMEDIATE，MySQL 用 SELECT ... FOR UPDATE，
因此两个请求同时抢同一座位时只有一个能成功。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..config import config
from ..db import IntegrityError
from ..errors import ConflictError, NotFound
from ..repositories import reservation_repository as repo
from ..repositories import seat_repository, violation_repository
from . import auth_service
from .slot_rules import (
    CHECKIN_EARLY,
    CHECKIN_LATE,
    checkin_window_text,
    evaluate_checkin_window,
    parse_slot,
)
from .violation_service import KIND_NO_SHOW, Verdict, ViolationService

CANCELLABLE = ("booked",)
CHECKABLE = ("booked",)
FINISHABLE = ("booked", "checked_in")


class ReservationService:
    def __init__(self, db, cfg=config, violation_service: ViolationService | None = None) -> None:
        self.db = db
        self.cfg = cfg
        self.violations = violation_service or ViolationService(db, cfg)

    # ---------- 查询 ----------
    def list_seats(self, day: str, start: str, end: str) -> list[dict]:
        """返回座位列表 + 该时段可用性（一次查询算出占用集合）。"""
        with self.db.session() as session:
            seats = seat_repository.list_all(session)
            busy = repo.busy_seat_ids(session, day, start, end)
        result = []
        for seat in seats:
            item = dict(seat)
            if seat["status"] != "available":
                item["available"] = False
                item["status_label"] = "维护中"
            elif int(seat["id"]) in busy:
                item["available"] = False
                item["status_label"] = "已占用"
            else:
                item["available"] = True
                item["status_label"] = "可预约"
            result.append(item)
        return result

    def list_mine(self, actor: dict) -> list[dict]:
        with self.db.session() as session:
            rows = repo.list_by_user(session, actor["id"])
        for row in rows:
            row["checkin_window"] = checkin_window_text(
                row, self.cfg.checkin_early_minutes, self.cfg.no_show_grace_minutes
            )
        return rows

    # ---------- 写操作 ----------
    def create(self, actor: dict, seat_id, day, start, end) -> dict:
        slot = parse_slot(day, start, end)

        with self.db.session(write=True) as session:
            # 顺序很重要：锁座位必须是事务里的第一条语句。
            # MySQL 的 REPEATABLE READ 在第一次普通读时建立读视图，
            # 若先做违规阈值查询，读视图会早于锁建立，
            # 后续冲突检查就读不到并发事务刚提交的预约 —— 会造成同一座位双订。
            seat = seat_repository.lock(session, seat_id)
            if not seat:
                raise NotFound("座位不存在")
            if seat["status"] != "available":
                raise ConflictError("该座位正在维护，暂不可预约")

            self._ensure_no_blocking_violation(session, actor["id"])

            if repo.find_overlap(session, seat_id, slot.day_text, slot.start_text, slot.end_text):
                raise ConflictError("该座位在所选时段已被预约，请选择其他座位")
            if repo.count_active_same_slot(
                session, actor["id"], slot.day_text, slot.start_text, slot.end_text
            ):
                raise ConflictError("你在该时段已有其他预约，请先取消或更换时段")

            try:
                reservation_id = repo.create(
                    session, actor["id"], seat_id, slot.day_text, slot.start_text, slot.end_text
                )
            except IntegrityError as exc:
                # 唯一键兜底：并发下同一用户同一时段重复提交
                raise ConflictError("预约重复或数据冲突") from exc

            detail = repo.get_detail(session, reservation_id)
        return detail

    def cancel(self, reservation_id, actor: dict) -> str:
        with self.db.session(write=True) as session:
            reservation = repo.get(session, reservation_id)
            if not reservation:
                raise NotFound("预约不存在")
            auth_service.ensure_owner_or_admin(actor, reservation["user_id"])
            if reservation["status"] not in CANCELLABLE:
                raise ConflictError("当前状态不能取消")
            repo.set_status(session, reservation_id, "cancelled")
        return "预约已取消"

    def checkin(self, reservation_id, actor: dict, now: datetime | None = None) -> dict:
        rejection = None
        detail = None

        with self.db.session(write=True) as session:
            reservation = repo.get_detail(session, reservation_id)
            if not reservation:
                raise NotFound("预约不存在")
            auth_service.ensure_owner_or_admin(actor, reservation["user_id"])
            if reservation["status"] not in CHECKABLE:
                raise ConflictError("当前预约状态不能签到")

            moment = now or datetime.now()
            window_state = "ok"
            if self.cfg.checkin_enforced:
                window_state = evaluate_checkin_window(
                    reservation,
                    moment,
                    self.cfg.checkin_early_minutes,
                    self.cfg.no_show_grace_minutes,
                )

            if window_state == CHECKIN_EARLY:
                window = checkin_window_text(
                    reservation, self.cfg.checkin_early_minutes, self.cfg.no_show_grace_minutes
                )
                raise ConflictError(f"还未到签到时间，可签到时段为 {window}")
            elif window_state == CHECKIN_LATE:
                # 超过签到截止时间：直接判失效并记违规（与定时扫描同一套规则）
                start = datetime.strptime(
                    f"{reservation['reservation_date']} {reservation['start_time']}",
                    "%Y-%m-%d %H:%M",
                )
                late_minutes = int((moment - start).total_seconds() // 60)
                self.violations.apply(
                    session, reservation, Verdict(KIND_NO_SHOW, "expired", late_minutes)
                )
                # 注意：不能在这里 raise，否则事务回滚会撤销上面的违规记录
                rejection = "已超过签到截止时间，预约已失效并记录违规"
            else:
                repo.set_status(session, reservation_id, "checked_in", mark_checkin=True)
                detail = repo.get_detail(session, reservation_id)

        if rejection:
            raise ConflictError(rejection)
        return {"message": "签到成功", "reservation": detail}

    def checkout(self, reservation_id, actor: dict) -> dict:
        with self.db.session(write=True) as session:
            reservation = repo.get(session, reservation_id)
            if not reservation:
                raise NotFound("预约不存在")
            auth_service.ensure_owner_or_admin(actor, reservation["user_id"])
            if reservation["status"] not in FINISHABLE:
                raise ConflictError("当前预约状态不能结束")
            repo.set_status(session, reservation_id, "completed")
            detail = repo.get_detail(session, reservation_id)
        return {"message": "本次自习已结束", "reservation": detail}

    # ---------- 内部校验 ----------
    def _ensure_no_blocking_violation(self, session, user_id) -> None:
        """近 N 天内未处理的违规达到阈值时，限制继续预约。"""
        since = (datetime.now() - timedelta(days=self.cfg.violation_window_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        count = violation_repository.count_open_since(session, user_id, since)
        if count >= self.cfg.violation_block_threshold:
            raise ConflictError(
                f"你在近 {self.cfg.violation_window_days} 天内有 {count} 条未处理的违规记录，"
                "请联系管理员处理后再预约"
            )


def today_text() -> str:
    return date.today().isoformat()
