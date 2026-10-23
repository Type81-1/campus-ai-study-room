"""静态一致性测试：MySQL 与 SQLite 两套脚本必须结构对齐。

防止「只改了其中一套建表脚本」导致的方言漂移——这正是迁移到 MySQL 时最容易出的问题。
"""
from __future__ import annotations

import re
import unittest

from tests import base  # noqa: F401  （负责 sys.path）

from backend.config import DATABASE_DIR

TABLE_PATTERN = re.compile(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", re.IGNORECASE)
SEAT_PATTERN = re.compile(r"\('([1-9]F-\d{2})'")


def read(dialect: str, name: str) -> str:
    return (DATABASE_DIR / dialect / name).read_text(encoding="utf-8")


class SchemaConsistencyTest(unittest.TestCase):
    def test_table_sets_match(self):
        mysql_tables = set(TABLE_PATTERN.findall(read("mysql", "schema.sql")))
        sqlite_tables = set(TABLE_PATTERN.findall(read("sqlite", "schema.sql")))
        self.assertEqual(mysql_tables, sqlite_tables)
        self.assertEqual(mysql_tables, {"users", "sessions", "seats", "reservations", "violations"})

    def test_seed_seats_match(self):
        mysql_seats = SEAT_PATTERN.findall(read("mysql", "seed.sql"))
        sqlite_seats = SEAT_PATTERN.findall(read("sqlite", "seed.sql"))
        self.assertEqual(mysql_seats, sqlite_seats)
        self.assertEqual(len(mysql_seats), 24)

    def test_both_seed_define_same_demo_accounts(self):
        for dialect in ("mysql", "sqlite"):
            content = read(dialect, "seed.sql")
            for username in ("student001", "student002", "admin"):
                with self.subTest(dialect=dialect, username=username):
                    self.assertIn(f"'{username}'", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
