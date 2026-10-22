"""业务规则：只做纯计算，不访问数据库，便于单元测试。

时段规则（需求中的「时段锁定」）：
- 只能预约当天及以后；
- 起止时间按整点 / 半点；
- 结束必须晚于开始，单次最长 4 小时。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..errors import ValidationError

MAX_DURATION = timedelta(hours=4)
ALLOWED_MINUTES = (0, 30)


@dataclass(frozen=True)
class Slot:
    day: date
    start: datetime
    end: datetime

    @property
    def day_text(self) -> str:
        return self.day.isoformat()

    @property
    def start_text(self) -> str:
        return self.start.strftime("%H:%M")

    @property
    def end_text(self) -> str:
        return self.end.strftime("%H:%M")

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def parse_slot(day_text, start_text, end_text, now: datetime | None = None) -> Slot:
    """解析并校验时段，不合法时抛 ValidationError。"""
    now = now or datetime.now()
    if not day_text or not start_text or not end_text:
        raise ValidationError("缺少时间参数")

    try:
        day = datetime.strptime(str(day_text), "%Y-%m-%d").date()
        start = datetime.strptime(f"{day_text} {start_text}", "%Y-%m-%d %H:%M")
        end = datetime.strptime(f"{day_text} {end_text}", "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ValidationError("日期或时间格式错误") from exc

    if day < now.date():
        raise ValidationError("不能预约过去的日期")
    if end <= start:
        raise ValidationError("结束时间必须晚于开始时间")
    if end - start > MAX_DURATION:
        raise ValidationError("单次预约最长 4 小时")
    if start.minute not in ALLOWED_MINUTES or end.minute not in ALLOWED_MINUTES:
        raise ValidationError("时间必须按整点或半小时填写")
    return Slot(day=day, start=start, end=end)


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """半开区间相交判定：[start, end) 与 [start, end) 是否重叠。"""
    return a_start < b_end and a_end > b_start
