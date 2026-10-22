"""后台定时任务：周期性扫描超时预约并生成违规预警。

独立守护线程，和 HTTP 请求线程共用同一个服务实例；
扫描本身就是幂等的，即使手动接口同时触发也不会重复记违规。
"""
from __future__ import annotations

import threading
import traceback

from .services.violation_service import ViolationService


class ViolationSweeper(threading.Thread):
    def __init__(self, service: ViolationService, interval: int = 60, verbose: bool = True) -> None:
        super().__init__(name="violation-sweeper", daemon=True)
        self.service = service
        self.interval = max(int(interval), 5)
        self.verbose = verbose
        self._stop_event = threading.Event()

    def run(self) -> None:
        if self.verbose:
            print(f"违规预警扫描已启动，间隔 {self.interval} 秒")
        while not self._stop_event.wait(self.interval):
            self.scan_once()

    def scan_once(self) -> dict | None:
        try:
            summary = self.service.scan()
            if self.verbose and (summary["violations"] or summary["expired"] or summary["overstay"]):
                print(
                    f"[违规扫描] 失效 {summary['expired']} 条，超时占用 {summary['overstay']} 条，"
                    f"新增违规 {summary['violations']} 条"
                )
            return summary
        except Exception:
            traceback.print_exc()
            return None

    def stop(self) -> None:
        self._stop_event.set()
