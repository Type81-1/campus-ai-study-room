"""MySQL 实机自检与压测。

本机没有 MySQL 时也可以直接跑，脚本会给出明确提示；有 MySQL（本机或 docker compose）
时，一条命令完成「建表 → 行锁验证 → 并发压测」三件事。

用法：
    # 方式一：docker compose up -d（推荐，库和账号都是现成的）
    docker compose up -d
    python scripts/mysql_check.py --password studyroom

    # 方式二：已有 MySQL 实例
    python scripts/mysql_check.py --host 10.0.0.5 --user root --password *** --database campus_study_room

    # 只做连接与建表自检，不跑压测
    python scripts/mysql_check.py --skip-load

输出：建表结果、索引数量、行锁并发结果、压测吞吐与延迟。
退出码：0 全部通过，1 有失败项或环境不可用。
"""
from __future__ import annotations

import argparse
import copy
import os
import statistics
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def parse_args():
    parser = argparse.ArgumentParser(description="MySQL 实机自检与压测")
    parser.add_argument("--host", default=os.environ.get("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.environ.get("MYSQL_USER", "root"))
    parser.add_argument("--password", default=os.environ.get("MYSQL_PASSWORD", "studyroom"))
    parser.add_argument("--database", default=os.environ.get("MYSQL_DATABASE", "campus_study_room"))
    parser.add_argument("--threads", type=int, default=20, help="压测线程数")
    parser.add_argument("--skip-load", action="store_true", help="只做连接与建表自检")
    return parser.parse_args()


def fail(message: str) -> int:
    print(f"[失败] {message}")
    return 1


def ensure_database(args) -> bool:
    try:
        import pymysql
    except ImportError:
        print("[缺少依赖] 请先执行：pip install -r backend/requirements.txt")
        return False
    try:
        conn = pymysql.connect(
            host=args.host, port=args.port, user=args.user, password=args.password,
            charset="utf8mb4", autocommit=True, connect_timeout=5,
        )
    except Exception as exc:
        print(f"[连接失败] {args.host}:{args.port} → {exc}")
        print("  可选方案：")
        print("    1) docker compose up -d           # 启动自带的 MySQL 8")
        print("    2) python scripts/init_mysql.py   # 初始化本机 MySQL")
        print("    3) 检查 --host / --port / --user / --password")
        return False

    with conn.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{args.database}` "
            "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
    conn.close()
    print(f"[连接成功] MySQL {version}，数据库 {args.database}")
    return True


def build_database(args):
    from backend.config import config
    from backend.db import Database

    cfg = copy.copy(config)
    cfg.db_backend = "mysql"
    cfg.mysql_host = args.host
    cfg.mysql_port = args.port
    cfg.mysql_user = args.user
    cfg.mysql_password = args.password
    cfg.mysql_database = args.database

    db = Database(cfg)
    db.initialize()
    return db, cfg


def check_schema(db) -> bool:
    with db.session() as session:
        tables = session.query_all(
            "SELECT TABLE_NAME AS name FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
        )
        names = {row["name"] for row in tables}
        indexes = session.query_one(
            "SELECT COUNT(*) AS total FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE()"
        )
        users = session.query_one("SELECT COUNT(*) AS total FROM users")
        seats = session.query_one("SELECT COUNT(*) AS total FROM seats")
        engine = session.query_one(
            "SELECT ENGINE AS engine FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reservations'"
        )

    expected = {"users", "sessions", "seats", "reservations", "violations"}
    missing = expected - names
    ok = not missing
    print(f"[建表自检] 表 {len(names)} 个：{', '.join(sorted(names))}")
    print(f"          索引 {indexes['total']} 个，users {users['total']} 条，seats {seats['total']} 条")
    print(f"          reservations 引擎：{engine['engine']}（应为 InnoDB，否则行锁失效）")
    if missing:
        print(f"[失败] 缺少表：{', '.join(sorted(missing))}")
    if (engine["engine"] or "").lower() != "innodb":
        print("[失败] reservations 不是 InnoDB，SELECT ... FOR UPDATE 不生效")
        ok = False
    return ok


def _new_seat(db, code: str) -> int:
    """每次运行都新建座位，避免上一次压测留下的预约干扰判断。"""
    with db.session(write=True) as session:
        return session.insert(
            "INSERT INTO seats (code,floor,zone,seat_type,near_window,power,status) "
            "VALUES (?,?,?,?,?,?,'available')",
            (code, 9, "验证区", "standard", 0, 1),
        )


def check_row_lock(db) -> bool:
    """两个用户同时抢同一座位：验证 FOR UPDATE 行锁确实只放行一个。"""
    from backend.api.router import Api
    from backend.repositories import session_repository
    from backend.security import hash_password, new_token, token_digest

    from backend.errors import AppError

    api = Api(db)
    day = (date.today() + timedelta(days=2)).isoformat()
    seat_id = _new_seat(db, f"LK{int(time.time()) % 100000}")
    hashed = hash_password("123456")
    expires = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    tokens = []
    with db.session(write=True) as session:
        for index in range(2):
            uid = session.insert(
                "INSERT INTO users (username,password,name,role,preferences) "
                "VALUES (?,?,?,'student','{}')",
                (f"lockcheck{int(time.time())}{index}", hashed, f"行锁验证{index}"),
            )
            token = new_token()
            session_repository.create(session, uid, token_digest(token), expires)
            tokens.append(token)

    barrier = threading.Barrier(2)
    results: list[int] = []
    lock = threading.Lock()

    errors: list[str] = []

    def worker(token):
        barrier.wait()
        try:
            status = api.handle(
                "POST", "/api/reservations", {},
                {"seat_id": seat_id, "reservation_date": day, "start_time": "09:00", "end_time": "11:00"},
                token=token,
            )[0]
        except AppError as exc:  # 业务异常按 HTTP 语义计入状态码
            status = exc.status
        except Exception as exc:  # 真实故障
            status = 0
            with lock:
                errors.append(f"{type(exc).__name__}: {exc}")
        with lock:
            results.append(status)

    threads = [threading.Thread(target=worker, args=(token,)) for token in tokens]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    ok = results.count(201) == 1 and results.count(409) == 1
    print(f"[行锁验证] 两人同抢一个座位（座位 {seat_id}）→ 状态码 {sorted(results)}（期望 [201, 409]）")
    if not ok:
        print("[失败] 行锁未生效，出现双订或异常")
        for item in errors[:3]:
            print(f"       异常：{item}")
    return ok


def run_load(db, threads: int) -> bool:
    from backend.api.router import Api
    from backend.repositories import session_repository
    from backend.security import hash_password, new_token, token_digest

    from backend.errors import AppError

    api = Api(db)
    day = (date.today() + timedelta(days=3)).isoformat()
    hashed = hash_password("123456")
    expires = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    tokens = []
    with db.session(write=True) as session:
        for index in range(threads):
            uid = session.insert(
                "INSERT INTO users (username,password,name,role,preferences) "
                "VALUES (?,?,?,'student','{}')",
                (f"myload{int(time.time())}{index:03d}", hashed, f"压测{index:03d}"),
            )
            token = new_token()
            session_repository.create(session, uid, token_digest(token), expires)
            tokens.append(token)

    stamp = int(time.time())
    seat_ids = [_new_seat(db, f"LD{stamp % 100000}{index:02d}") for index in range(threads)]

    barrier = threading.Barrier(threads)
    latencies: list[float] = []
    statuses: dict[int, int] = {}
    load_errors: list[str] = []
    lock = threading.Lock()

    def worker(token, seat_id):
        barrier.wait()
        started = time.perf_counter()
        code = 0
        try:
            code = api.handle(
                "POST", "/api/reservations", {},
                {"seat_id": seat_id, "reservation_date": day, "start_time": "15:00", "end_time": "17:00"},
                token=token,
            )[0]
        except AppError as exc:
            code = exc.status
        except Exception as exc:
            with lock:
                load_errors.append(f"{type(exc).__name__}: {exc}")
            code = 0
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            with lock:
                latencies.append(elapsed)
                statuses[code] = statuses.get(code, 0) + 1

    started = time.perf_counter()
    workers = [threading.Thread(target=worker, args=(t, s)) for t, s in zip(tokens, seat_ids)]
    for item in workers:
        item.start()
    for item in workers:
        item.join()
    wall = time.perf_counter() - started

    ok = statuses.get(201, 0) == threads
    print(
        f"[并发压测] {threads} 线程抢不同座位 → 成功 {statuses.get(201, 0)}/{threads}，"
        f"耗时 {wall:.2f}s，吞吐 {threads / wall:.1f} req/s，"
        f"平均 {statistics.mean(latencies):.0f}ms"
    )
    if not ok:
        print(f"[失败] 状态码分布 {statuses}")
        for item in load_errors[:3]:
            print(f"       异常：{item}")
    return ok


def main() -> int:
    args = parse_args()
    print("校园 AI 智能自习室 —— MySQL 实机自检")
    print(f"  目标：mysql://{args.user}@{args.host}:{args.port}/{args.database}")
    if not ensure_database(args):
        return 1

    db, _ = build_database(args)
    checks = [check_schema(db)]
    checks.append(check_row_lock(db))
    if not args.skip_load:
        checks.append(run_load(db, args.threads))

    passed = sum(1 for item in checks if item)
    print(f"\n===== 结果：{passed}/{len(checks)} 项通过 =====")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
