"""数据访问底座。

职责只有三件事：
1. 连接管理（SQLite 直连 / MySQL 连接池）；
2. 事务与加锁（SQLite 用 BEGIN IMMEDIATE 串行化写，MySQL 用行锁）；
3. 方言适配（占位符 ? → %s、结果值归一化），让上层仓储只写一份 SQL。

上层不感知具体数据库，只面向 Session 的 execute/query_* 方法。
"""
from __future__ import annotations

import queue
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from .config import DATABASE_DIR, config


class IntegrityError(Exception):
    """唯一键 / 外键冲突（屏蔽具体驱动的异常类型）。"""


class DatabaseError(Exception):
    """连接或执行失败。"""


def _normalize_value(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, timedelta):        # PyMySQL 把 TIME 列读成 timedelta
        total_minutes = int(value.total_seconds()) // 60
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
    if isinstance(value, Decimal):
        return float(value)
    return value


def _normalize_row(row):
    if row is None:
        return None
    return {key: _normalize_value(value) for key, value in dict(row).items()}


def split_sql(sql_text: str) -> list[str]:
    """把 .sql 文件拆成单条语句：去掉整行注释后按分号切分。"""
    cleaned = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--") or stripped.startswith("#"):
            continue
        cleaned.append(line)
    statements = []
    for chunk in "\n".join(cleaned).split(";"):
        statement = chunk.strip()
        if statement:
            statements.append(statement)
    return statements


class Result:
    """对游标的最小封装，统一 SQLite 与 PyMySQL 的差异。"""

    __slots__ = ("_cursor", "rowcount", "lastrowid")

    def __init__(self, cursor) -> None:
        self._cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = cursor.lastrowid

    def fetchone(self) -> dict | None:
        return _normalize_row(self._cursor.fetchone())

    def fetchall(self) -> list[dict]:
        return [_normalize_row(row) for row in self._cursor.fetchall()]


class Session:
    """一次数据库会话：一次请求（或一次服务调用）对应一个 Session。"""

    def __init__(self, raw, dialect: str, backend) -> None:
        self._raw = raw
        self.dialect = dialect
        self._backend = backend

    # ---- SQL 执行 ----
    def _adapt(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.dialect == "mysql" else sql

    def execute(self, sql: str, params=()) -> Result:
        adapted = self._adapt(sql)
        try:
            if self.dialect == "mysql":
                cursor = self._raw.cursor()
                cursor.execute(adapted, tuple(params) or None)
            else:
                cursor = self._raw.execute(adapted, tuple(params) or ())
            return Result(cursor)
        except sqlite3.IntegrityError as exc:              # SQLite
            raise IntegrityError(str(exc)) from exc
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc
        except Exception as exc:                            # PyMySQL 的 IntegrityError
            if exc.__class__.__name__ in ("IntegrityError", "DataError"):
                raise IntegrityError(str(exc)) from exc
            raise DatabaseError(str(exc)) from exc

    def query_one(self, sql: str, params=()) -> dict | None:
        return self.execute(sql, params).fetchone()

    def query_all(self, sql: str, params=()) -> list[dict]:
        return self.execute(sql, params).fetchall()

    def insert(self, sql: str, params=()) -> int:
        return self.execute(sql, params).lastrowid

    # ---- 行锁：MySQL 显式 FOR UPDATE，SQLite 由 BEGIN IMMEDIATE 在库级串行化 ----
    def lock_row(self, table: str, row_id) -> dict | None:
        if self.dialect == "mysql":
            return self.query_one(f"SELECT * FROM {table} WHERE id=? FOR UPDATE", (row_id,))
        return self.query_one(f"SELECT * FROM {table} WHERE id=?", (row_id,))

    # ---- 事务 ----
    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        try:
            self._raw.rollback()
        except Exception:
            pass

    def close(self) -> None:
        self._backend.release(self._raw, self.dialect)


class _MySQLPool:
    """极简连接池：避免每个请求重建 TCP 连接拖累并发表现。"""

    def __init__(self, factory, size: int) -> None:
        self._factory = factory
        self._idle: queue.LifoQueue = queue.LifoQueue(maxsize=max(size, 1))
        self._size = max(size, 1)
        self._created = 0
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 8.0):
        try:
            conn = self._idle.get_nowait()
            try:
                conn.ping()  # 探活；PyMySQL 1.1 起 reconnect 参数已废弃，失败就重建连接
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                return self._factory()
        except queue.Empty:
            pass
        with self._lock:
            if self._created < self._size:
                self._created += 1
                return self._factory()
        return self._idle.get(timeout=timeout)

    def release(self, conn) -> None:
        try:
            self._idle.put_nowait(conn)
        except queue.Full:
            try:
                conn.close()
            finally:
                with self._lock:
                    self._created -= 1


class Database:
    def __init__(self, cfg=config) -> None:
        self.config = cfg
        self.dialect = cfg.db_backend
        self._pool: _MySQLPool | None = None
        if self.dialect == "mysql":
            self._pool = _MySQLPool(self._connect_mysql, cfg.mysql_pool_size)
        else:
            cfg.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- 连接 ----
    def _connect_mysql(self):
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as exc:  # pragma: no cover - 依赖缺失时给出明确指引
            raise DatabaseError(
                "缺少 MySQL 驱动，请先执行：pip install -r backend/requirements.txt"
            ) from exc
        return pymysql.connect(
            host=self.config.mysql_host,
            port=self.config.mysql_port,
            user=self.config.mysql_user,
            password=self.config.mysql_password,
            database=self.config.mysql_database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=5,
        )

    def _connect_sqlite(self):
        conn = sqlite3.connect(self.config.sqlite_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        # NORMAL 只牺牲「操作系统崩溃」时的持久性，不影响进程崩溃；换来写入吞吐明显提升
        conn.execute("PRAGMA synchronous = NORMAL")
        # journal_mode 只在初始化时设一次：并发连接上重复执行需要排他锁，
        # 会在其他连接持有写锁时报 "attempt to write a readonly database"。
        return conn

    def acquire(self):
        if self.dialect == "mysql":
            assert self._pool is not None
            return self._pool.acquire()
        return self._connect_sqlite()

    def release(self, conn, dialect: str) -> None:
        if dialect == "mysql":
            assert self._pool is not None
            self._pool.release(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def session(self, write: bool = False):
        """获取会话。

        write=True 时开启写事务：SQLite 用 BEGIN IMMEDIATE 直接拿写锁（避免
        「先查冲突再插入」之间的竞态），MySQL 由调用方对关键行 SELECT ... FOR UPDATE。
        """
        raw = self.acquire()
        session = Session(raw, self.dialect, self)
        try:
            if self.dialect == "sqlite" and write:
                raw.execute("BEGIN IMMEDIATE")
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- 初始化 ----
    def initialize(self) -> None:
        schema_file = DATABASE_DIR / self.dialect / "schema.sql"
        seed_file = DATABASE_DIR / self.dialect / "seed.sql"
        if not schema_file.is_file():
            raise DatabaseError(f"找不到建表脚本：{schema_file}")
        if self.dialect == "sqlite":
            # 说明：这里刻意不开 WAL。WAL 依赖 -shm 共享内存，在部分 Windows /
            # 虚拟文件系统上并发 BEGIN IMMEDIATE 会报 "attempt to write a readonly
            # database"。改用回滚日志 + busy_timeout，由 SQLite 自身串行化写入，
            # 正确性优先；真正的高并发场景由 MySQL 侧的行锁承担。
            raw = self._connect_sqlite()
            try:
                raw.execute("PRAGMA journal_mode = DELETE")
            finally:
                raw.close()
        with self.session(write=True) as session:
            for statement in split_sql(schema_file.read_text(encoding="utf-8")):
                session.execute(statement)
            empty = session.query_one("SELECT COUNT(*) AS total FROM users")
            if empty and int(empty["total"]) == 0 and seed_file.is_file():
                for statement in split_sql(seed_file.read_text(encoding="utf-8")):
                    session.execute(statement)

    def ping(self) -> bool:
        with self.session() as session:
            session.query_one("SELECT 1 AS ok")
        return True
