"""运行配置。

所有可变项都通过环境变量注入，便于在 SQLite（本地演示）与 MySQL（正式部署）之间切换，
不修改任何代码即可换库。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent          # backend/
ROOT_DIR = BASE_DIR.parent                          # 项目根目录
FRONTEND_DIR = ROOT_DIR / "frontend"
DATABASE_DIR = ROOT_DIR / "database"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


class Config:
    """进程级配置（模块导入时按环境变量求值一次）。"""

    def __init__(self) -> None:
        # ---- 静态资源目录 ----
        self.frontend_dir: Path = FRONTEND_DIR

        # ---- 服务监听 ----
        self.host: str = _env("HOST", "127.0.0.1") or "127.0.0.1"
        self.port: int = _env_int("PORT", 8000)

        # ---- 数据库选型 ----
        # DB_BACKEND 显式指定 mysql / sqlite；未指定时：配了 MYSQL_HOST 就走 MySQL，否则 SQLite。
        explicit = (_env("DB_BACKEND") or "").lower()
        if explicit in ("mysql", "sqlite"):
            self.db_backend = explicit
        else:
            self.db_backend = "mysql" if _env("MYSQL_HOST") else "sqlite"

        self.sqlite_path: Path = Path(_env("STUDY_ROOM_DB", BASE_DIR / "data" / "study_room.db"))

        self.mysql_host: str = _env("MYSQL_HOST", "127.0.0.1") or "127.0.0.1"
        self.mysql_port: int = _env_int("MYSQL_PORT", 3306)
        self.mysql_user: str = _env("MYSQL_USER", "root") or "root"
        self.mysql_password: str = _env("MYSQL_PASSWORD", "") or ""
        self.mysql_database: str = _env("MYSQL_DATABASE", "campus_study_room") or "campus_study_room"
        self.mysql_pool_size: int = _env_int("MYSQL_POOL_SIZE", 8)

        # ---- 鉴权 ----
        # 登录令牌有效期（天）；令牌只以 SHA-256 摘要入库
        self.session_ttl_days: int = _env_int("SESSION_TTL_DAYS", 7)
        # 允许跨域来源，部署时收敛成具体域名
        self.cors_origin: str = _env("CORS_ORIGIN", "*") or "*"

        # ---- 实时推送（SSE） ----
        self.sse_heartbeat_seconds: int = _env_int("SSE_HEARTBEAT_SECONDS", 15)
        self.sse_max_clients: int = _env_int("SSE_MAX_CLIENTS", 50)

        # ---- 违规预警规则 ----
        # 预约开始后超过 N 分钟仍未签到 → 判定「超时未签到」
        self.no_show_grace_minutes: int = _env_int("NO_SHOW_GRACE_MINUTES", 15)
        # 预约结束后超过 N 分钟仍未结束自习 → 判定「超时占用」
        self.overstay_grace_minutes: int = _env_int("OVERSTAY_GRACE_MINUTES", 30)
        # 签到时间窗口：开始前 N 分钟开放签到（过晚则判超时未签到）
        self.checkin_early_minutes: int = _env_int("CHECKIN_EARLY_MINUTES", 30)
        # 是否强制校验签到窗口；测试或演示可用 CHECKIN_ENFORCED=0 关闭
        self.checkin_enforced: bool = (_env("CHECKIN_ENFORCED", "1") or "1") not in ("0", "false", "False")
        # 违规统计窗口（天）与触发预约限制的阈值
        self.violation_window_days: int = _env_int("VIOLATION_WINDOW_DAYS", 30)
        self.violation_block_threshold: int = _env_int("VIOLATION_BLOCK_THRESHOLD", 3)
        # 后台扫描任务间隔（秒），0 表示不启动后台线程
        self.sweeper_interval: int = _env_int("SWEEPER_INTERVAL", 60)

        # ---- 其他 ----
        self.request_body_limit: int = _env_int("REQUEST_BODY_LIMIT", 1_000_000)

    # 便于日志与 /api/health 展示
    def describe(self) -> dict:
        if self.db_backend == "mysql":
            target = f"mysql://{self.mysql_user}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        else:
            target = f"sqlite://{self.sqlite_path}"
        return {
            "backend": self.db_backend,
            "database": target,
            "no_show_grace_minutes": self.no_show_grace_minutes,
            "overstay_grace_minutes": self.overstay_grace_minutes,
            "violation_block_threshold": self.violation_block_threshold,
            "checkin_early_minutes": self.checkin_early_minutes,
            "session_ttl_days": self.session_ttl_days,
        }


config = Config()
