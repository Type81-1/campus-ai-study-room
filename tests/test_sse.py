"""SSE 实时推送的 HTTP 层测试。

用裸 socket 直连真实服务，验证：
- 未带令牌 / 令牌无效时拒绝；
- 合法令牌能拿到 text/event-stream 并收到首帧；
- 业务事件发布后能推送到已连接的客户端。
"""
from __future__ import annotations

import json
import socket
import threading
import unittest

from tests.base import make_api
from backend.events import bus
from backend.web import make_server


class SseTest(unittest.TestCase):
    def setUp(self) -> None:
        bus.reset()
        self.db, self.api = make_api()
        self.api.cfg.sse_heartbeat_seconds = 1
        self.server = make_server(self.api, "127.0.0.1", 0, cfg=self.api.cfg, quiet=True)
        self.host, self.port = self.server.server_address[0], self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        status, body = self.api.handle(
            "POST", "/api/login", {}, {"username": "student001", "password": "123456"}
        )
        self.token = body["token"]
        self.sockets: list[socket.socket] = []

    def tearDown(self) -> None:
        for sock in self.sockets:
            try:
                sock.close()
            except OSError:
                pass
        self.server.shutdown()
        self.server.server_close()
        bus.reset()

    # ---- 工具 ----
    def _connect(self, path: str, timeout: float = 5.0):
        sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sockets.append(sock)
        request = (
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            "Accept: text/event-stream\r\nConnection: keep-alive\r\n\r\n"
        )
        sock.sendall(request.encode())
        return sock

    def _read_until(self, sock: socket.socket, marker: bytes, limit: int = 65536) -> bytes:
        buffer = b""
        while marker not in buffer and len(buffer) < limit:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer += chunk
        return buffer

    # ---- 用例 ----
    def test_requires_token(self):
        sock = self._connect("/api/events")
        data = self._read_until(sock, b"}", limit=4096)
        self.assertIn(b"401", data.split(b"\r\n")[0])
        self.assertIn("请先登录".encode(), data)

    def test_rejects_invalid_token(self):
        sock = self._connect("/api/events?token=not-a-token")
        data = self._read_until(sock, b"}", limit=4096)
        self.assertIn(b"401", data.split(b"\r\n")[0])

    def test_stream_headers_and_hello(self):
        sock = self._connect(f"/api/events?token={self.token}")
        data = self._read_until(sock, b"connected as")
        head, _, body = data.partition(b"\r\n\r\n")
        self.assertIn(b"200", head.split(b"\r\n")[0])
        self.assertIn(b"text/event-stream", head)
        self.assertIn(b"chunked", head.lower())
        self.assertIn(b"connected as student001", body)

    def test_event_is_pushed_to_client(self):
        sock = self._connect(f"/api/events?token={self.token}")
        self._read_until(sock, b"connected as")

        bus.publish("seat.status", {"seat_id": 7, "status": "maintenance"})
        data = self._read_until(sock, b"seat.status")
        self.assertIn(b"event: seat.status", data)
        self.assertIn(b'"seat_id": 7', data)

    def test_reservation_event_is_published(self):
        sock = self._connect(f"/api/events?token={self.token}")
        self._read_until(sock, b"connected as")

        self.api.handle(
            "POST",
            "/api/reservations",
            {},
            {
                "seat_id": 3,
                "reservation_date": "2099-01-01",
                "start_time": "09:00",
                "end_time": "11:00",
            },
            token=self.token,
        )
        data = self._read_until(sock, b"reservation.created")
        self.assertIn(b"event: reservation.created", data)
        payload = json.loads(data.split(b"data: ", 1)[1].split(b"\r\n", 1)[0].decode("utf-8"))
        self.assertEqual(payload["seat_id"], 3)

    def test_heartbeat_keeps_connection_alive(self):
        sock = self._connect(f"/api/events?token={self.token}")
        self._read_until(sock, b"connected as")
        data = self._read_until(sock, b"ping", limit=8192)
        self.assertIn(b"ping", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
