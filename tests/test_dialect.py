"""单元测试：数据底座（方言适配、脚本解析、结果归一化）。

这部分不依赖任何数据库实例，用来锁定「一套 SQL 跑两种库」的关键转换逻辑，
MySQL 环境不可用时也能回归。
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from tests import base  # noqa: F401

from backend.config import DATABASE_DIR
from backend.db import Session, _normalize_row, _normalize_value, split_sql


class _DummyBackend:
    def release(self, conn, dialect):
        pass


def make_session(dialect: str) -> Session:
    return Session(raw=None, dialect=dialect, backend=_DummyBackend())


class PlaceholderTest(unittest.TestCase):
    def test_mysql_translates_qmark_to_ps(self):
        session = make_session("mysql")
        self.assertEqual(
            session._adapt("SELECT * FROM seats WHERE id=? AND code=?"),
            "SELECT * FROM seats WHERE id=%s AND code=%s",
        )

    def test_sqlite_keeps_qmark(self):
        session = make_session("sqlite")
        sql = "SELECT * FROM seats WHERE id=?"
        self.assertEqual(session._adapt(sql), sql)


class NormalizeTest(unittest.TestCase):
    def test_datetime_to_second_precision(self):
        self.assertEqual(
            _normalize_value(datetime(2026, 5, 11, 9, 30, 15)), "2026-05-11 09:30:15"
        )

    def test_date_and_time(self):
        self.assertEqual(_normalize_value(date(2026, 5, 11)), "2026-05-11")
        self.assertEqual(_normalize_value(time(9, 30)), "09:30")

    def test_mysql_time_returns_timedelta(self):
        self.assertEqual(_normalize_value(timedelta(hours=9, minutes=30)), "09:30")
        self.assertEqual(_normalize_value(timedelta(0)), "00:00")

    def test_decimal_to_float(self):
        self.assertEqual(_normalize_value(Decimal("12.50")), 12.5)

    def test_row_mapping(self):
        row = {"id": 1, "start_time": timedelta(hours=9), "created_at": datetime(2026, 5, 11, 8, 0)}
        self.assertEqual(
            _normalize_row(row),
            {"id": 1, "start_time": "09:00", "created_at": "2026-05-11 08:00:00"},
        )
        self.assertIsNone(_normalize_row(None))


class SplitSqlTest(unittest.TestCase):
    def test_split_skips_comments_and_blank(self):
        script = """
        -- 注释行
        CREATE TABLE a (id INT);
        # 另一种注释
        INSERT INTO a VALUES (1);

        """
        statements = split_sql(script)
        self.assertEqual(len(statements), 2)
        self.assertTrue(statements[0].startswith("CREATE TABLE"))
        self.assertIn("INSERT INTO", statements[1])

    def test_mysql_schema_yields_four_tables(self):
        schema = (DATABASE_DIR / "mysql" / "schema.sql").read_text(encoding="utf-8")
        statements = split_sql(schema)
        self.assertEqual(len(statements), 4)
        self.assertTrue(all("CREATE TABLE IF NOT EXISTS" in s for s in statements))

    def test_sqlite_schema_yields_tables_and_indexes(self):
        schema = (DATABASE_DIR / "sqlite" / "schema.sql").read_text(encoding="utf-8")
        statements = split_sql(schema)
        self.assertEqual(sum("CREATE TABLE" in s for s in statements), 4)
        self.assertEqual(sum("CREATE INDEX" in s for s in statements), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
