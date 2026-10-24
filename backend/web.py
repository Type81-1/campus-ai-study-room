"""HTTP 传输层：只负责收发，不包含业务逻辑。

- JSON 入参解析与体积限制
- 业务异常 → 状态码 / 统一 JSON 结构
- 静态页面托管（frontend/）
"""
from __future__ import annotations

import json
import queue
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import config
from .errors import AppError
from .events import TooManySubscribers, bus
from .api.router import Api

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}


def make_handler(api: Api, cfg=config, quiet: bool = False):
    class StudyRoomHandler(BaseHTTPRequestHandler):
        server_version = "StudyRoom/2.0"
        protocol_version = "HTTP/1.1"

        # ---------------- 基础输出 ----------------
        def _write(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _send_json(self, payload: dict, status: int = 200) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._write(status, raw, "application/json; charset=utf-8")

        def _read_token(self) -> str | None:
            """从 Authorization: Bearer <token> 或 X-Auth-Token 取令牌。"""
            header = self.headers.get("Authorization") or ""
            if header.lower().startswith("bearer "):
                return header[7:].strip() or None
            return self.headers.get("X-Auth-Token") or None

        # ---------------- SSE 实时事件 ----------------
        def _sse_chunk(self, text: str) -> None:
            data = text.encode("utf-8")
            self.wfile.write(f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n")
            self.wfile.flush()

        def _stream_events(self, query: dict) -> None:
            """/api/events：Server-Sent Events 长连接。

            EventSource 无法自定义请求头，因此这里允许用 ?token= 传令牌；
            令牌仍是短期有效的会话令牌，且只读事件流不涉及写操作。
            """
            token = (query.get("token") or [None])[0] or self._read_token()
            try:
                actor = api.authenticate(token)
            except AppError as exc:
                self._send_json({"ok": False, "code": exc.code, "message": exc.message}, exc.status)
                return

            try:
                channel = bus.subscribe()
            except TooManySubscribers as exc:
                self._send_json({"ok": False, "message": str(exc)}, 503)
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "close")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.close_connection = True

            try:
                self._sse_chunk(f": connected as {actor['username']}\n\n")
                self._sse_chunk("retry: 3000\n\n")
                while True:
                    try:
                        event = channel.get(timeout=cfg.sse_heartbeat_seconds)
                    except queue.Empty:
                        self._sse_chunk(": ping\n\n")
                        continue
                    payload = json.dumps(event, ensure_ascii=False)
                    self._sse_chunk(f"event: {event['type']}\ndata: {payload}\n\n")
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                bus.unsubscribe(channel)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > cfg.request_body_limit:
                raise AppError("请求体过大", status=413)
            if not length:
                return {}
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AppError("请求体不是合法 JSON") from exc
            if not isinstance(data, dict):
                raise AppError("请求体必须是 JSON 对象")
            return data

        # ---------------- 路由 ----------------
        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)

            if path == "/api/events":
                if method != "GET":
                    self._send_json({"ok": False, "message": "仅支持 GET"}, 405)
                else:
                    self._stream_events(query)
                return

            if not path.startswith("/api/"):
                if method == "GET":
                    self._serve_static(path)
                else:
                    self._send_json({"ok": False, "message": "资源不存在"}, 404)
                return

            try:
                payload = self._read_json() if method in ("POST", "PUT", "PATCH") else {}
                status, body = api.handle(method, path, query, payload, token=self._read_token())
                self._send_json(body, status)
            except AppError as exc:
                self._send_json({"ok": False, "code": exc.code, "message": exc.message}, exc.status)
            except Exception as exc:  # 兜底：不让异常栈冲垮连接
                traceback.print_exc()
                self._send_json({"ok": False, "message": f"服务器内部错误：{exc}"}, 500)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", cfg.cors_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Auth-Token")
            self.send_header("Content-Length", "0")
            self.end_headers()

        # ---------------- 静态资源 ----------------
        def _serve_static(self, path: str) -> None:
            relative = "index.html" if path == "/" else path.lstrip("/")
            root = cfg.frontend_dir.resolve()
            target = (root / relative).resolve()
            if root not in target.parents and target != root:
                self._send_json({"ok": False, "message": "非法路径"}, 400)
                return
            if not target.is_file():
                self._send_json({"ok": False, "message": "页面不存在"}, 404)
                return
            self._write(200, target.read_bytes(), CONTENT_TYPES.get(target.suffix, "application/octet-stream"))

        def log_message(self, fmt, *args):  # 保持一行式访问日志
            if not quiet:
                print(f"[{self.log_date_time_string()}] {fmt % args}")

    return StudyRoomHandler


class StudyRoomServer(ThreadingHTTPServer):
    """并发相关参数：默认 backlog 只有 5，几十个连接同时到达会触发 SYN 重传
    （表现为约 1 秒的延迟尖刺），这里放大到 128。"""

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128


def make_server(api: Api, host: str, port: int, cfg=config, quiet: bool = False) -> ThreadingHTTPServer:
    return StudyRoomServer((host, port), make_handler(api, cfg, quiet))
