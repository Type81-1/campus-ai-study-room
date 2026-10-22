"""测试公共装配：所有用例默认跑在临时 SQLite 库上，不碰开发数据。

若需要验证 MySQL，设置 MYSQL_HOST 等环境变量并指定 TEST_DB_BACKEND=mysql，
测试会直接在你的 MySQL 实例上建表（表结构与生产一致）。
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP_DIR = pathlib.Path(tempfile.mkdtemp(prefix="study_room_test_"))

os.environ.setdefault("DB_BACKEND", os.environ.get("TEST_DB_BACKEND", "sqlite"))
os.environ.setdefault("STUDY_ROOM_DB", str(_TMP_DIR / "default.db"))
os.environ.setdefault("SWEEPER_INTERVAL", "0")

import copy  # noqa: E402
import unittest  # noqa: E402
from datetime import date, timedelta  # noqa: E402

from backend.api.router import Api  # noqa: E402
from backend.config import config  # noqa: E402
from backend.db import Database  # noqa: E402


def future_day(offset: int = 1) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def today_text() -> str:
    return date.today().isoformat()


def make_api():
    """每个用例一套干净库。"""
    if config.db_backend == "mysql":
        db = Database(config)
        db.initialize()
        _truncate(db)
        return db, Api(db)

    fd, raw_path = tempfile.mkstemp(suffix=".db", dir=str(_TMP_DIR))
    os.close(fd)
    cfg = copy.copy(config)
    cfg.db_backend = "sqlite"
    cfg.sqlite_path = pathlib.Path(raw_path)
    cfg.sweeper_interval = 0
    db = Database(cfg)
    db.initialize()
    return db, Api(db)


def _truncate(db):
    with db.session(write=True) as session:
        for table in ("violations", "reservations", "users", "seats"):
            session.execute(f"DELETE FROM {table}")
        for statement in ("INSERT INTO users (username,password,name,role,preferences) VALUES "
                          "('student001','123456','演示学生','student','{\"window\": true, \"power\": true}')",
                          "INSERT INTO users (username,password,name,role,preferences) VALUES "
                          "('student002','123456','测试同学','student','{\"window\": false, \"power\": true}')",
                          "INSERT INTO users (username,password,name,role,preferences) VALUES "
                          "('admin','admin123','系统管理员','admin','{}')"):
            session.execute(statement)
        for floor in (1, 2, 3):
            for index in range(1, 9):
                code = f"{floor}F-{index:02d}"
                zone = "靠窗区" if index <= 4 else "安静区"
                session.execute(
                    "INSERT INTO seats (code,floor,zone,seat_type,near_window,power,status) "
                    "VALUES (?,?,?,?,?,?,'available')",
                    (code, floor, zone, "standard", int(index <= 4), int(index % 3 != 0)),
                )


def add_users(db, count: int) -> list[int]:
    """批量创建学生，用于并发用例。"""
    ids = []
    with db.session(write=True) as session:
        for index in range(count):
            ids.append(
                session.insert(
                    "INSERT INTO users (username,password,name,role,preferences) "
                    "VALUES (?,?,?,'student','{}')",
                    (f"loadtest{index:03d}", "123456", f"压测用户{index:03d}"),
                )
            )
    return ids


class ApiTestCase(unittest.TestCase):
    """集成用例基类：直接调用 Api.handle，不经过网络层，聚焦业务。"""

    def setUp(self) -> None:
        self.db, self.api = make_api()

    def call(self, method: str, path: str, query: dict | None = None, payload: dict | None = None):
        from backend.errors import AppError

        try:
            return self.api.handle(method, path, query or {}, payload or {})
        except AppError as exc:  # 与 web 层一致：业务异常翻译成状态码
            return exc.status, {"ok": False, "code": exc.code, "message": exc.message}

    def post(self, path: str, payload: dict):
        return self.call("POST", path, None, payload)

    def get(self, path: str, query: dict | None = None):
        return self.call("GET", path, query)

    def book(self, user_id: int, seat_id: int, day: str | None = None, start="09:00", end="11:00"):
        return self.post(
            "/api/reservations",
            {
                "user_id": user_id,
                "seat_id": seat_id,
                "reservation_date": day or future_day(),
                "start_time": start,
                "end_time": end,
            },
        )
