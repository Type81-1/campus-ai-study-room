"""给演示 / 前端冒烟测试准备一点真实数据（预约、签到、违规）。

用法（先启动后端）：
    python scripts/seed_demo.py
    python scripts/seed_demo.py http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def call(method, path, payload=None, token=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def login(username, password):
    status, body = call("POST", "/api/login", {"username": username, "password": password})
    if status != 200:
        raise SystemExit(f"登录失败：{body}")
    return body["token"]


def main() -> int:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    student1 = login("student001", "123456")
    student2 = login("student002", "123456")
    admin = login("admin", "admin123")

    for seat, start, end in [(1, "09:00", "11:00"), (5, "13:00", "15:00"), (9, "19:00", "21:00")]:
        status, _ = call("POST", "/api/reservations", {
            "seat_id": seat, "reservation_date": tomorrow,
            "start_time": start, "end_time": end}, student1)
        print(f"student001 预约 {seat} 号座位：HTTP {status}")

    status, _ = call("POST", "/api/reservations", {
        "seat_id": 2, "reservation_date": tomorrow,
        "start_time": "09:00", "end_time": "11:00"}, student2)
    print(f"student002 预约 2 号座位：HTTP {status}")

    # 今天的早场 → 触发一条「超时未签到」违规
    status, _ = call("POST", "/api/reservations", {
        "seat_id": 7, "reservation_date": date.today().isoformat(),
        "start_time": "00:00", "end_time": "02:00"}, student2)
    print(f"student002 预约今天的早场：HTTP {status}")

    status, body = call("POST", "/api/admin/violations/scan", {}, admin)
    print(f"触发违规扫描：HTTP {status} {body.get('summary')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
