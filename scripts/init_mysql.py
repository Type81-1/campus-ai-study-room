"""初始化 MySQL：创建数据库、执行建表脚本与演示数据。

适用于本机已装 MySQL（或 docker compose 起了 MySQL）但不想手动敲 SQL 的场景。
运行：
    pip install -r backend/requirements.txt
    python scripts/init_mysql.py
    python scripts/init_mysql.py --host 127.0.0.1 --user root --password studyroom

脚本是幂等的：表用 CREATE TABLE IF NOT EXISTS，数据用 INSERT IGNORE。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.db import split_sql  # noqa: E402

SCHEMA = ROOT / "database" / "mysql" / "schema.sql"
SEED = ROOT / "database" / "mysql" / "seed.sql"


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 MySQL 数据库")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="studyroom")
    parser.add_argument("--database", default="campus_study_room")
    args = parser.parse_args()

    try:
        import pymysql
    except ImportError:
        print("缺少 PyMySQL，请先执行：pip install -r backend/requirements.txt")
        return 1

    print(f"连接 MySQL {args.user}@{args.host}:{args.port} ...")
    server = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with server.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{args.database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        print(f"数据库 {args.database} 就绪")
    finally:
        server.close()

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            for label, path in (("建表", SCHEMA), ("初始化数据", SEED)):
                statements = split_sql(path.read_text(encoding="utf-8"))
                for statement in statements:
                    cursor.execute(statement)
                print(f"{label}：执行 {len(statements)} 条语句")
            cursor.execute("SELECT COUNT(*) FROM users")
            users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM seats")
            seats = cursor.fetchone()[0]
    finally:
        conn.close()

    print(f"完成：users {users} 条，seats {seats} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
