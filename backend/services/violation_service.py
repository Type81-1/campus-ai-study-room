"""违规占座预警模块（后台管理模块的核心能力）。

两类规则：
- no_show  超时未签到：预约开始后超过 NO_SHOW_GRACE_MINUTES 分钟仍未签到
           → 预约置为 expired，生成违规记录；
- overstay 超时占用：签到后超过结束时间 OVERSTAY_GRACE_MINUTES 分钟仍未结束
           → 预约置为 completed，生成违规记录。

扫描是幂等的：状态变更后 reservation 不再命中待扫描集合，
且 violations 表对 (reservation_id, kind) 建了唯一键，重复扫描不会重复记违规。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import config
from ..db import IntegrityError
from ..errors import NotFound
from ..repositories import reservation_repository as reservation_repo
from ..repositories import violation_repository as violation_repo

KIND_NO_SHOW = "no_show"
KIND_OVERSTAY = "overstay"


@dataclass(frozen=True)
class Verdict:
    kind: str
    next_status: str
    late_minutes: int


def _combine(day: str, clock: str) -> datetime:
    return datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M")


def decide(reservation: dict, now: datetime, no_show_grace: int, overstay_grace: int) -> Verdict | None:
    """纯规则判定：给定一条预约和当前时间，判断是否构成违规。"""
    status = reservation["status"]
    start = _combine(reservation["reservation_date"], reservation["start_time"])
    end = _combine(reservation["reservation_date"], reservation["end_time"])

    if status == "booked":
        deadline = start + timedelta(minutes=no_show_grace)
        if now >= deadline:
            return Verdict(KIND_NO_SHOW, "expired", int((now - start).total_seconds() // 60))

    if status == "checked_in":
        deadline = end + timedelta(minutes=overstay_grace)
        if now >= deadline:
            return Verdict(KIND_OVERSTAY, "completed", int((now - end).total_seconds() // 60))

    return None


def build_message(kind: str, reservation: dict, late_minutes: int, grace: int) -> str:
    seat = reservation.get("seat_code") or f"座位 {reservation.get('seat_id')}"
    window = f"{reservation['reservation_date']} {reservation['start_time']}-{reservation['end_time']}"
    if kind == KIND_NO_SHOW:
        return f"预约 {seat}（{window}）超过签到宽限 {grace} 分钟未签到，超时 {late_minutes} 分钟，预约已自动失效"
    return f"预约 {seat}（{window}）超过结束时间 {late_minutes} 分钟仍未办理结束，已自动结束并记违规"


class ViolationService:
    def __init__(self, db, cfg=config) -> None:
        self.db = db
        self.cfg = cfg

    # ---------- 扫描 ----------
    def scan(self, now: datetime | None = None) -> dict:
        now = now or datetime.now()
        summary = {"scanned": 0, "expired": 0, "overstay": 0, "violations": 0}

        with self.db.session(write=True) as session:
            pending = reservation_repo.list_sweepable(session, now.date().isoformat())
            summary["scanned"] = len(pending)
            for reservation in pending:
                verdict = decide(
                    reservation,
                    now,
                    self.cfg.no_show_grace_minutes,
                    self.cfg.overstay_grace_minutes,
                )
                if verdict is None:
                    continue
                reservation_repo.set_status(session, reservation["id"], verdict.next_status)
                grace = (
                    self.cfg.no_show_grace_minutes
                    if verdict.kind == KIND_NO_SHOW
                    else self.cfg.overstay_grace_minutes
                )
                try:
                    violation_repo.create(
                        session,
                        reservation["user_id"],
                        reservation["id"],
                        verdict.kind,
                        build_message(verdict.kind, reservation, verdict.late_minutes, grace),
                    )
                    summary["violations"] += 1
                except IntegrityError:
                    pass  # 该预约的同类违规已存在，幂等跳过
                summary["expired" if verdict.kind == KIND_NO_SHOW else "overstay"] += 1

        return summary

    # ---------- 查询 / 处理 ----------
    def list_all(self) -> list[dict]:
        with self.db.session() as session:
            return violation_repo.list_all(session)

    def resolve(self, violation_id) -> str:
        with self.db.session(write=True) as session:
            if not violation_repo.get(session, violation_id):
                raise NotFound("违规记录不存在")
            updated = violation_repo.resolve(session, violation_id)
        if updated == 0:
            raise NotFound("违规记录已处理或不存在")
        return "违规记录已处理"
