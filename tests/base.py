"""测试公共装配：所有用例默认跑在临时 SQLite 库上，不碰开发数据。

若需要验证 MySQL，设置 MYSQL_HOST 等环境变量并指定 TEST_DB_BACKEND=mysql，
测试会直接在你的 MySQL 实例上建表（表结构与生产一致）。

约定：
- 每个用例一套全新库，演示账号口令在建库时被迁移成 PBKDF2 哈希；
- 默认关闭签到窗口校验（`checkin_enforced=False`），让与时间无关的用例稳定，
  签到窗口本身由专门的用例类打开开关验证。
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
os.environ.setdefault("CHECKIN_ENFORCED", "0")
# 测试里把 PBKDF2 迭代次数调低，避免几百次登录把用例拖到分钟级
os.environ.setdefault("PBKDF2_ITERATIONS", "1000")

import copy  # noqa: E402
import unittest  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402

from backend.api.router import Api  # noqa: E402
from backend.config import config  # noqa: E402
from backend.db import Database  # noqa: E402
from backend.repositories import session_repository, user_repository  # noqa: E402
from backend.security import hash_password, new_token, token_digest  # noqa: E402
from backend.services.auth_service import migrate_plaintext_passwords  # noqa: E402

DEMO_PASSWORD = "123456"
# 同一口令只算一次哈希，避免每个测试用户都跑一遍 PBKDF2
_CACHED_HASH: str | None = None


def demo_hash() -> str:
    global _CACHED_HASH
    if _CACHED_HASH is None:
        _CACHED_HASH = hash_password(DEMO_PASSWORD)
    return _CACHED_HASH


def future_day(offset: int = 1) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def today_text() -> str:
    return date.today().isoformat()


def make_api(checkin_enforced: bool = False, **overrides):
    """每个用例一套干净库，返回 (db, api)；api.cfg 可按需再调。"""
    if config.db_backend == "mysql":
        db = Database(config)
        db.initialize()
        _truncate(db)
        migrate_plaintext_passwords(db)
        api = Api(db, config)
        api.cfg.checkin_enforced = checkin_enforced
        return db, api

    fd, raw_path = tempfile.mkstemp(suffix=".db", dir=str(_TMP_DIR))
    os.close(fd)
    cfg = copy.copy(config)
    cfg.db_backend = "sqlite"
    cfg.sqlite_path = pathlib.Path(raw_path)
    cfg.sweeper_interval = 0
    cfg.checkin_enforced = checkin_enforced
    for key, value in overrides.items():
        setattr(cfg, key, value)

    db = Database(cfg)
    db.initialize()
    migrate_plaintext_passwords(db)
    return db, Api(db, cfg)


def _truncate(db):
    with db.session(write=True) as session:
        for table in ("sessions", "violations", "reservations", "users", "seats"):
            session.execute(f"DELETE FROM {table}")
        if db.dialect == "mysql":
            # DELETE 不会重置自增，用例里按固定 id（1~24）引用座位会 404
            for table in ("sessions", "violations", "reservations", "users", "seats"):
                session.execute(f"ALTER TABLE {table} AUTO_INCREMENT = 1")
        for statement in (
            "INSERT INTO users (username,password,name,role,preferences) VALUES "
            "('student001','123456','演示学生','student','{\"window\": true, \"power\": true}')",
            "INSERT INTO users (username,password,name,role,preferences) VALUES "
            "('student002','123456','测试同学','student','{\"window\": false, \"power\": true}')",
            "INSERT INTO users (username,password,name,role,preferences) VALUES "
            "('admin','admin123','系统管理员','admin','{}')",
        ):
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


def add_users(db, count: int, prefix: str = "loadtest") -> list[int]:
    """批量创建学生（口令统一为 123456，只算一次哈希）。"""
    hashed = demo_hash()
    ids = []
    with db.session(write=True) as session:
        for index in range(count):
            ids.append(
                session.insert(
                    "INSERT INTO users (username,password,name,role,preferences) "
                    "VALUES (?,?,?,'student','{}')",
                    (f"{prefix}{index:03d}", hashed, f"测试用户{index:03d}"),
                )
            )
    return ids


def issue_token(db, user_id, ttl_days: int = 7) -> str:
    """直接签发令牌（跳过口令校验），供并发用例快速准备身份。"""
    token = new_token()
    expires_at = (datetime.now() + timedelta(days=ttl_days)).strftime("%Y-%m-%d %H:%M:%S")
    with db.session(write=True) as session:
        session_repository.create(session, user_id, token_digest(token), expires_at)
    return token


def get_actor(db, username: str) -> dict:
    with db.session() as session:
        user = user_repository.get_by_username_with_secret(session, username)
    user.pop("password", None)
    return user


_DEFAULT = object()


class ApiTestCase(unittest.TestCase):
    """集成用例基类：直接调用 Api.handle，不经过网络层，聚焦业务。"""

    checkin_enforced = False

    def setUp(self) -> None:
        self.db, self.api = make_api(checkin_enforced=self.checkin_enforced)
        self.tokens = {
            "student001": self.login("student001", DEMO_PASSWORD),
            "student002": self.login("student002", DEMO_PASSWORD),
            "admin": self.login("admin", "admin123"),
        }

    # ---- 身份 ----
    def login(self, username: str, password: str) -> str:
        status, body = self.call(
            "POST", "/api/login", payload={"username": username, "password": password},
            token=None,
        )
        self.assertEqual(status, 200, body)
        return body["token"]

    def actor(self, username: str = "student001") -> dict:
        return get_actor(self.db, username)

    # ---- 请求 ----
    def call(self, method: str, path: str, query: dict | None = None, payload: dict | None = None, token=_DEFAULT):
        from backend.errors import AppError

        if token is _DEFAULT:
            token = self.tokens["student001"]
        try:
            return self.api.handle(method, path, query or {}, payload or {}, token=token)
        except AppError as exc:  # 与 web 层一致：业务异常翻译成状态码
            return exc.status, {"ok": False, "code": exc.code, "message": exc.message}

    def post(self, path: str, payload: dict, token=_DEFAULT):
        return self.call("POST", path, None, payload, token=token)

    def get(self, path: str, query: dict | None = None, token=_DEFAULT):
        return self.call("GET", path, query, None, token=token)

    def book(self, seat_id: int, day: str | None = None, start="09:00", end="11:00", token=_DEFAULT):
        return self.post(
            "/api/reservations",
            {
                "seat_id": seat_id,
                "reservation_date": day or future_day(),
                "start_time": start,
                "end_time": end,
            },
            token=token,
        )
