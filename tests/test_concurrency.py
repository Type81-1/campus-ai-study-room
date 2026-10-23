"""并发测试：验证「抢座」在并发下不会双订。

对应任务书「并发场景压力测试」与「预约冲突拦截」两项要求。
用例在临时 SQLite 库上跑，写事务由 BEGIN IMMEDIATE 串行化；
切到 MySQL 后同一套逻辑由 SELECT ... FOR UPDATE 保证。

身份：每个线程使用独立令牌（直接签发，不跑口令哈希，避免拖慢并发起跑）。
"""
from __future__ import annotations

import threading
import time
import unittest

from tests.base import ApiTestCase, add_users, future_day, issue_token
from backend.errors import AppError


def book_once(api, token, seat_id, day, start="09:00", end="11:00"):
    payload = {
        "seat_id": seat_id,
        "reservation_date": day,
        "start_time": start,
        "end_time": end,
    }
    try:
        return api.handle("POST", "/api/reservations", {}, payload, token=token)[0]
    except AppError as exc:
        return exc.status


class ConcurrentBookingTest(ApiTestCase):
    THREADS = 20

    def setUp(self) -> None:
        super().setUp()
        self.users = add_users(self.db, self.THREADS)
        self.tokens = [issue_token(self.db, uid) for uid in self.users]
        self.day = future_day()

    def _run_parallel(self, tasks):
        barrier = threading.Barrier(len(tasks))
        results: list[int] = []
        lock = threading.Lock()

        def worker(index):
            barrier.wait()
            status = tasks[index]()
            with lock:
                results.append(status)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(tasks))]
        started = time.perf_counter()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        elapsed = time.perf_counter() - started
        return results, elapsed

    def test_same_seat_only_one_winner(self):
        """20 个用户同时抢同一个座位同一时段：只能有 1 个成功。"""
        tasks = [
            (lambda token=token: book_once(self.api, token, 1, self.day)) for token in self.tokens
        ]
        results, elapsed = self._run_parallel(tasks)

        self.assertEqual(results.count(201), 1, f"出现重复预订：{results}")
        self.assertEqual(results.count(409), len(self.users) - 1)

        with self.db.session() as session:
            row = session.query_one(
                "SELECT COUNT(*) AS total FROM reservations WHERE seat_id=? "
                "AND reservation_date=? AND status IN ('booked','checked_in')",
                (1, self.day),
            )
        self.assertEqual(int(row["total"]), 1)
        print(f"\n  [并发] 同一座位 20 并发 → 1 成功 / {len(self.users) - 1} 冲突，耗时 {elapsed:.2f}s")

    def test_same_user_same_slot_only_once(self):
        """同一用户并发提交同一时段的不同座位：也只能成功 1 次。"""
        token = self.tokens[0]
        tasks = [
            (lambda seat=seat: book_once(self.api, token, seat, self.day))
            for seat in range(1, self.THREADS + 1)
        ]
        results, elapsed = self._run_parallel(tasks)

        self.assertEqual(results.count(201), 1, f"同一用户被重复预订：{results}")

        with self.db.session() as session:
            row = session.query_one(
                "SELECT COUNT(*) AS total FROM reservations WHERE user_id=? "
                "AND reservation_date=? AND status IN ('booked','checked_in')",
                (self.users[0], self.day),
            )
        self.assertEqual(int(row["total"]), 1)
        print(f"\n  [并发] 同一用户 20 并发 → 1 成功，耗时 {elapsed:.2f}s")

    def test_different_seats_all_succeed(self):
        """20 个用户抢 20 个不同座位：应全部成功。"""
        tasks = [
            (lambda token=token, seat=seat: book_once(self.api, token, seat, self.day))
            for token, seat in zip(self.tokens, range(1, self.THREADS + 1))
        ]
        results, elapsed = self._run_parallel(tasks)

        self.assertEqual(results.count(201), self.THREADS, f"出现失败：{results}")
        with self.db.session() as session:
            row = session.query_one(
                "SELECT COUNT(*) AS total FROM reservations WHERE reservation_date=?",
                (self.day,),
            )
        self.assertEqual(int(row["total"]), self.THREADS)
        print(f"\n  [并发] 20 座位 20 并发 → 全部成功，耗时 {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main(verbosity=2)
