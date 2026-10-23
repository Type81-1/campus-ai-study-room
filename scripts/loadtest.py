"""并发压力测试脚本（HTTP 层）。

与 tests/test_concurrency.py 的区别：这里走真实 HTTP、真实线程服务器，
测出的是端到端的吞吐与延迟，用于测试报告的「并发场景压力测试」一节。

鉴权：脚本直接为压测用户签发令牌（跳过口令哈希），请求统一带 Bearer 头。

用法：
    python scripts/loadtest.py
    python scripts/loadtest.py --users 50 --rounds 3 --reads 100
    DB_BACKEND=mysql MYSQL_HOST=127.0.0.1 MYSQL_USER=root MYSQL_PASSWORD=xxx \
        python scripts/loadtest.py

脚本会自己起一个临时服务（随机端口），SQLite 模式下用临时库，不影响开发数据。
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import statistics
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DB_BACKEND", os.environ.get("TEST_DB_BACKEND", "sqlite"))
if os.environ["DB_BACKEND"] == "sqlite":
    os.environ.setdefault("SWEEPER_INTERVAL", "0")
    # 压测永远用临时库，避免污染 backend/data/study_room.db
    import tempfile

    os.environ["STUDY_ROOM_DB"] = tempfile.mktemp(prefix="study_room_load_", suffix=".db")
# 压测账号的口令哈希不必消耗真实迭代次数
os.environ.setdefault("PBKDF2_ITERATIONS", "1000")

from backend.app import bootstrap  # noqa: E402
from backend.config import config  # noqa: E402
from backend.repositories import session_repository  # noqa: E402
from backend.security import hash_password, new_token, token_digest  # noqa: E402
from backend.web import make_server  # noqa: E402


class Client:
    """一次请求一个连接：http.client 的连接不是线程安全的，不能跨线程共享。"""

    def __init__(self, host: str, port: int, token: str | None = None) -> None:
        self.host = host
        self.port = port
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        conn = http.client.HTTPConnection(self.host, self.port, timeout=60)
        try:
            body = json.dumps(payload).encode() if payload is not None else None
            headers = {}
            if body:
                headers["Content-Type"] = "application/json"
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            raw = response.read()
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {"raw": raw[:200].decode("utf-8", "replace")}
            return response.status, data
        finally:
            conn.close()


def seed_users(db, count: int) -> list[str]:
    """批量建压测用户并直接签发令牌，返回令牌列表。"""
    suffix = str(int(time.time()))[-5:]
    hashed = hash_password("123456")
    expires_at = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    tokens = []
    with db.session(write=True) as session:
        for index in range(count):
            user_id = session.insert(
                "INSERT INTO users (username,password,name,role,preferences) "
                "VALUES (?,?,?,'student','{}')",
                (f"load{suffix}{index:04d}", hashed, f"压测用户{index:04d}"),
            )
            token = new_token()
            session_repository.create(session, user_id, token_digest(token), expires_at)
            tokens.append(token)
    return tokens


def ensure_seats(db, count: int) -> int:
    """保证座位数不少于并发数（演示库默认只有 24 个）。"""
    with db.session() as session:
        total = int(session.query_one("SELECT COUNT(*) AS total FROM seats")["total"])
    if total >= count:
        return total
    with db.session(write=True) as session:
        for index in range(total + 1, count + 1):
            session.execute(
                "INSERT INTO seats (code,floor,zone,seat_type,near_window,power,status) "
                "VALUES (?,?,?,?,?,?,'available')",
                (f"LT-{index:03d}", (index - 1) // 8 + 1, "安静区", "standard", 0, 1),
            )
    return count


def run_parallel(host: str, port: int, tasks):
    """tasks: [(token, method, path, payload)] → ([(status, elapsed_ms, data)], wall_seconds)"""
    barrier = threading.Barrier(len(tasks))
    results: list[tuple[int, float, dict]] = []
    lock = threading.Lock()

    def worker(token, method, path, payload):
        client = Client(host, port, token)
        barrier.wait()
        started = time.perf_counter()
        try:
            status, data = client.request(method, path, payload)
        except Exception as exc:  # 连接层异常也计入错误
            status, data = 0, {"error": repr(exc)}
        elapsed = (time.perf_counter() - started) * 1000
        with lock:
            results.append((status, elapsed, data))

    threads = [threading.Thread(target=worker, args=task) for task in tasks]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results, time.perf_counter() - started


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(len(ordered) * ratio), len(ordered) - 1)
    return ordered[index]


def report(title: str, results, wall: float) -> dict:
    latencies = [item[1] for item in results]
    statuses: dict[int, int] = {}
    for status, _, _ in results:
        statuses[status] = statuses.get(status, 0) + 1
    total = len(results)
    throughput = total / wall if wall else 0

    print(f"\n== {title} ==")
    print(f"  请求数 {total}，总耗时 {wall:.2f}s，吞吐 {throughput:.1f} req/s")
    print(
        f"  延迟 平均 {statistics.mean(latencies):.1f}ms / "
        f"P50 {percentile(latencies, 0.5):.1f}ms / "
        f"P95 {percentile(latencies, 0.95):.1f}ms / "
        f"最大 {max(latencies):.1f}ms"
    )
    print("  状态码分布：" + "，".join(f"{code}×{count}" for code, count in sorted(statuses.items())))
    return {
        "title": title,
        "total": total,
        "wall": wall,
        "throughput": throughput,
        "avg": statistics.mean(latencies),
        "p50": percentile(latencies, 0.5),
        "p95": percentile(latencies, 0.95),
        "max": max(latencies),
        "statuses": statuses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校园自习室系统并发压力测试")
    parser.add_argument("--users", type=int, default=30, help="并发用户数（同时是抢座线程数）")
    parser.add_argument("--rounds", type=int, default=1, help="抢座场景重复轮数")
    parser.add_argument("--reads", type=int, default=60, help="座位查询场景请求数")
    args = parser.parse_args()

    db, api = bootstrap()
    tokens = seed_users(db, args.users)
    ensure_seats(db, args.users)
    server = make_server(api, "127.0.0.1", 0, quiet=True)
    host, port = server.server_address[0], server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    info = config.describe()
    print("校园 AI 智能自习室 —— 并发压力测试")
    print(f"  数据库：{info['database']}（{info['backend']}）")
    print(f"  并发线程：{args.users}，抢座轮数：{args.rounds}，查询请求：{args.reads}")
    print(f"  服务地址：http://{host}:{port}（Bearer 令牌鉴权）")

    summary = []
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # ---- 场景 1：同一座位，N 人同时抢（每轮换一个座位，避免被上一轮占住）----
    for round_index in range(1, args.rounds + 1):
        tasks = [
            (
                token,
                "POST",
                "/api/reservations",
                {
                    "seat_id": round_index,
                    "reservation_date": tomorrow,
                    "start_time": "09:00",
                    "end_time": "11:00",
                },
            )
            for token in tokens
        ]
        results, wall = run_parallel(host, port, tasks)
        stats = report(f"场景 1/{round_index}：{args.users} 人并发抢同一个座位", results, wall)
        succeeded = stats["statuses"].get(201, 0)
        conflicts = stats["statuses"].get(409, 0)
        print(f"  结果校验：成功 {succeeded}（期望 1），冲突 {conflicts}（期望 {args.users - 1}）")
        stats["passed"] = succeeded == 1 and conflicts == args.users - 1
        summary.append(stats)

    # ---- 场景 2：N 人抢 N 个不同座位，应全部成功 ----
    tasks = [
        (
            token,
            "POST",
            "/api/reservations",
            {
                "seat_id": index + 1,
                "reservation_date": tomorrow,
                "start_time": "13:00",
                "end_time": "15:00",
            },
        )
        for index, token in enumerate(tokens)
    ]
    results, wall = run_parallel(host, port, tasks)
    stats = report(f"场景 2：{args.users} 人并发抢 {args.users} 个不同座位", results, wall)
    succeeded = stats["statuses"].get(201, 0)
    print(f"  结果校验：成功 {succeeded}（期望 {args.users}）")
    stats["passed"] = succeeded == args.users
    summary.append(stats)

    # ---- 场景 3：座位查询（读多场景）----
    tasks = [
        (tokens[0], "GET", f"/api/seats?date={tomorrow}&start=13:00&end=15:00", None)
        for _ in range(args.reads)
    ]
    results, wall = run_parallel(host, port, tasks)
    stats = report(f"场景 3：{args.reads} 次并发座位查询", results, wall)
    stats["passed"] = stats["statuses"].get(200, 0) == args.reads
    print(f"  结果校验：200 共 {stats['statuses'].get(200, 0)} 次（期望 {args.reads}）")
    summary.append(stats)

    server.shutdown()
    server.server_close()

    failed = [item for item in summary if not item.get("passed", False)]
    print("\n===== 汇总 =====")
    for item in summary:
        flag = "通过" if item.get("passed") else "未通过"
        print(
            f"  [{flag}] {item['title']}：吞吐 {item['throughput']:.1f} req/s，"
            f"平均 {item['avg']:.1f}ms，P95 {item['p95']:.1f}ms"
        )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
