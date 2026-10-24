"""实时事件总线（SSE）单元测试。"""
from __future__ import annotations

import queue
import unittest

from tests import base  # noqa: F401

from backend.events import EventBus, TooManySubscribers


class EventBusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = EventBus(max_subscribers=3, queue_size=2)

    def test_publish_reaches_all_subscribers(self):
        first = self.bus.subscribe()
        second = self.bus.subscribe()
        delivered = self.bus.publish("seat_change", {"seat_id": 3})
        self.assertEqual(delivered, 2)
        for channel in (first, second):
            event = channel.get_nowait()
            self.assertEqual(event["type"], "seat_change")
            self.assertEqual(event["seat_id"], 3)

    def test_no_subscriber_returns_zero(self):
        self.assertEqual(self.bus.publish("seat_change"), 0)

    def test_unsubscribe_stops_delivery(self):
        channel = self.bus.subscribe()
        self.bus.unsubscribe(channel)
        self.assertEqual(self.bus.subscriber_count, 0)
        self.assertEqual(self.bus.publish("seat_change"), 0)

    def test_slow_subscriber_drops_oldest_instead_of_blocking(self):
        channel = self.bus.subscribe()
        for index in range(5):  # 队列容量 2，应保留最新两条
            self.bus.publish("seat_change", {"seq": index})
        self.assertEqual(channel.qsize(), 2)
        first = channel.get_nowait()
        second = channel.get_nowait()
        self.assertEqual(first["seq"], 3)
        self.assertEqual(second["seq"], 4)

    def test_subscriber_cap(self):
        for _ in range(3):
            self.bus.subscribe()
        with self.assertRaises(TooManySubscribers):
            self.bus.subscribe()

    def test_reset_clears_subscribers(self):
        self.bus.subscribe()
        self.bus.reset()
        self.assertEqual(self.bus.subscriber_count, 0)

    def test_event_payload_immutability(self):
        """publish 不应修改调用方传入的 payload。"""
        channel = self.bus.subscribe()
        payload = {"seat_id": 1}
        self.bus.publish("seat_change", payload)
        self.assertEqual(payload, {"seat_id": 1})
        self.assertEqual(channel.get_nowait()["type"], "seat_change")


if __name__ == "__main__":
    unittest.main(verbosity=2)
