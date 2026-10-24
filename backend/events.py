"""进程内事件总线（SSE 推送的数据源）。

设计取舍：
- 只支持单进程（课程设计部署场景足够）。多进程部署需换成 Redis Pub/Sub，接口保持不变即可；
- 发布方绝不阻塞：订阅队列满时丢弃最旧事件，避免慢客户端拖垮请求线程；
- 订阅数有上限，防止连接泄漏把线程占满。
"""
from __future__ import annotations

import queue
import threading

DEFAULT_MAX_SUBSCRIBERS = 50
DEFAULT_QUEUE_SIZE = 64


class TooManySubscribers(Exception):
    """SSE 连接数超过上限。"""


class EventBus:
    def __init__(self, max_subscribers: int = DEFAULT_MAX_SUBSCRIBERS, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        self.max_subscribers = max_subscribers
        self.queue_size = queue_size
        self._subscribers: set[queue.Queue] = set()
        self._lock = threading.Lock()

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def subscribe(self) -> queue.Queue:
        with self._lock:
            if len(self._subscribers) >= self.max_subscribers:
                raise TooManySubscribers(f"实时通道已满（上限 {self.max_subscribers}）")
            channel: queue.Queue = queue.Queue(maxsize=self.queue_size)
            self._subscribers.add(channel)
            return channel

    def unsubscribe(self, channel: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(channel)

    def publish(self, event_type: str, payload: dict | None = None) -> int:
        """广播事件，返回成功入队的订阅数。"""
        event = {"type": event_type, **(payload or {})}
        with self._lock:
            targets = list(self._subscribers)
        delivered = 0
        for channel in targets:
            try:
                channel.put_nowait(event)
                delivered += 1
            except queue.Full:
                try:  # 丢弃最旧事件，保证慢客户端不会卡住发布方
                    channel.get_nowait()
                    channel.put_nowait(event)
                    delivered += 1
                except queue.Empty:
                    pass
        return delivered

    def reset(self) -> None:
        """测试用：清空所有订阅。"""
        with self._lock:
            self._subscribers.clear()


bus = EventBus()
