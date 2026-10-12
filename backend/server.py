"""校园 AI 智能自习室预约系统后端。

仅使用 Python 标准库：sqlite3 + http.server，启动后同时提供 REST API 和前端页面。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = Path(os.environ.get("STUDY_ROOM_DB", DATA_DIR / "study_room.db"))
DATA_DIR.mkdir(exist_ok=True)


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db() -> None:
    conn = connect_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'admin')),
            preferences TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS seats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            floor INTEGER NOT NULL,
            zone TEXT NOT NULL,
            seat_type TEXT NOT NULL DEFAULT 'standard',
            near_window INTEGER NOT NULL DEFAULT 0,
            power INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'available'
        );
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            seat_id INTEGER NOT NULL REFERENCES seats(id),
            reservation_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'booked' CHECK(status IN ('booked','checked_in','completed','cancelled','expired')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            checkin_at TEXT,
            UNIQUE(user_id, reservation_date, start_time, end_time)
        );
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            reservation_id INTEGER REFERENCES reservations(id),
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_reservation_slot ON reservations(seat_id, reservation_date, start_time, end_time);
        CREATE INDEX IF NOT EXISTS idx_reservation_user ON reservations(user_id, reservation_date);
        """
    )
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO users(username,password,name,role,preferences) VALUES (?,?,?,?,?)",
            [
                ("student001", "123456", "演示学生", "student", json.dumps({"window": True, "power": True})),
                ("student002", "123456", "测试同学", "student", json.dumps({"window": False, "power": True})),
                ("admin", "admin123", "系统管理员", "admin", "{}"),
            ],
        )
    if conn.execute("SELECT COUNT(*) FROM seats").fetchone()[0] == 0:
        seats = []
        for floor in (1, 2, 3):
            for index in range(1, 9):
                seats.append((f"{floor}F-{index:02d}", floor, "靠窗区" if index <= 4 else "安静区", "standard", int(index <= 4), int(index % 3 != 0), "available"))
        conn.executemany("INSERT INTO seats(code,floor,zone,seat_type,near_window,power,status) VALUES (?,?,?,?,?,?,?)", seats)
    conn.commit()
    conn.close()


def row_dict(row: sqlite3.Row | None):
    return dict(row) if row else None


def json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length > 1_000_000:
        raise ValueError("请求体过大")
    raw = handler.rfile.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8"))


def send_json(handler, payload, status=HTTPStatus.OK):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(raw)


def fail(handler, message, status=HTTPStatus.BAD_REQUEST):
    send_json(handler, {"ok": False, "message": message}, status)


def get_user(conn, user_id):
    try:
        return conn.execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone()
    except (TypeError, ValueError):
        return None


def required(payload, fields):
    missing = [field for field in fields if payload.get(field) in (None, "")]
    if missing:
        raise ValueError("缺少字段：" + ", ".join(missing))


def valid_slot(reservation_date, start_time, end_time):
    try:
        start = datetime.strptime(f"{reservation_date} {start_time}", "%Y-%m-%d %H:%M")
        end = datetime.strptime(f"{reservation_date} {end_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None, "日期或时间格式错误"
    if start.date() < date.today():
        return None, "不能预约过去的日期"
    if end <= start:
        return None, "结束时间必须晚于开始时间"
    if (end - start).total_seconds() > 4 * 3600:
        return None, "单次预约最长 4 小时"
    if start.minute not in (0, 30) or end.minute not in (0, 30):
        return None, "时间必须按整点或半小时填写"
    return (start, end), None


def conflict(conn, seat_id, reservation_date, start_time, end_time, exclude_id=None):
    query = """SELECT id FROM reservations
               WHERE seat_id=? AND reservation_date=?
                 AND status IN ('booked','checked_in')
                 AND start_time < ? AND end_time > ?"""
    params = [seat_id, reservation_date, end_time, start_time]
    if exclude_id:
        query += " AND id != ?"
        params.append(exclude_id)
    return conn.execute(query, params).fetchone()


def reservation_view(conn, reservation_id):
    return conn.execute(
        """SELECT r.*, s.code seat_code, s.floor, s.zone, s.near_window, s.power,
                  u.name user_name, u.username
           FROM reservations r JOIN seats s ON s.id=r.seat_id JOIN users u ON u.id=r.user_id
           WHERE r.id=?""", (reservation_id,)
    ).fetchone()


def build_seats(conn, query):
    reservation_date = query.get("date", [date.today().isoformat()])[0]
    start_time = query.get("start", ["09:00"])[0]
    end_time = query.get("end", ["11:00"])[0]
    rows = conn.execute("SELECT * FROM seats ORDER BY floor, id").fetchall()
    result = []
    for seat in rows:
        busy = conflict(conn, seat["id"], reservation_date, start_time, end_time)
        item = row_dict(seat)
        item["available"] = busy is None
        item["status_label"] = "可预约" if item["available"] else "已占用"
        result.append(item)
    return result


class StudyRoomHandler(BaseHTTPRequestHandler):
    server_version = "StudyRoom/1.0"

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if path.startswith("/api/"):
            self.api_get(path, query)
        else:
            self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.api_post(parsed.path.rstrip("/"))
        else:
            fail(self, "资源不存在", HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.api_delete(parsed.path.rstrip("/"), parse_qs(parsed.query))
        else:
            fail(self, "资源不存在", HTTPStatus.NOT_FOUND)

    def serve_static(self, path):
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = (FRONTEND_DIR / relative).resolve()
        if FRONTEND_DIR.resolve() not in target.parents and target != FRONTEND_DIR.resolve():
            fail(self, "非法路径", HTTPStatus.BAD_REQUEST)
            return
        if not target.is_file():
            fail(self, "页面不存在", HTTPStatus.NOT_FOUND)
            return
        content_type = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}.get(target.suffix, "application/octet-stream")
        raw = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def api_get(self, path, query):
        conn = connect_db()
        try:
            if path == "/api/health":
                send_json(self, {"ok": True, "service": "study-room", "time": datetime.now().isoformat(timespec="seconds")})
            elif path == "/api/seats":
                send_json(self, {"ok": True, "seats": build_seats(conn, query)})
            elif path == "/api/reservations":
                user_id = query.get("user_id", [None])[0]
                if not user_id:
                    return fail(self, "需要 user_id")
                rows = conn.execute("""SELECT r.*, s.code seat_code, s.floor, s.zone
                    FROM reservations r JOIN seats s ON s.id=r.seat_id
                    WHERE r.user_id=? ORDER BY r.reservation_date DESC, r.start_time DESC""", (user_id,)).fetchall()
                send_json(self, {"ok": True, "reservations": [row_dict(row) for row in rows]})
            elif path == "/api/recommendations":
                self.recommendations(conn, query)
            elif path == "/api/admin/stats":
                self.admin_stats(conn, query)
            elif path == "/api/admin/violations":
                if not self.require_admin(conn, query.get("user_id", [None])[0]): return
                rows = conn.execute("""SELECT v.*, u.name user_name, u.username
                    FROM violations v JOIN users u ON u.id=v.user_id ORDER BY v.created_at DESC""").fetchall()
                send_json(self, {"ok": True, "violations": [row_dict(row) for row in rows]})
            elif path == "/api/admin/users":
                if not self.require_admin(conn, query.get("user_id", [None])[0]): return
                rows = conn.execute("SELECT id,username,name,role,created_at FROM users ORDER BY id").fetchall()
                send_json(self, {"ok": True, "users": [row_dict(row) for row in rows]})
            else:
                fail(self, "接口不存在", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            print("GET error:", repr(exc))
            fail(self, "服务器内部错误", HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            conn.close()

    def api_post(self, path):
        conn = connect_db()
        try:
            payload = json_body(self)
            if path == "/api/login":
                required(payload, ["username", "password"])
                user = conn.execute("SELECT id,username,name,role,preferences FROM users WHERE username=? AND password=?", (payload["username"], payload["password"])).fetchone()
                if not user: return fail(self, "账号或密码错误", HTTPStatus.UNAUTHORIZED)
                send_json(self, {"ok": True, "user": row_dict(user)})
            elif path == "/api/reservations":
                self.create_reservation(conn, payload)
            elif re.fullmatch(r"/api/reservations/\d+/checkin", path):
                reservation_id = int(path.split("/")[3])
                self.checkin(conn, reservation_id, payload)
            elif re.fullmatch(r"/api/reservations/\d+/checkout", path):
                reservation_id = int(path.split("/")[3])
                self.checkout(conn, reservation_id, payload)
            elif re.fullmatch(r"/api/admin/violations/\d+/resolve", path):
                violation_id = int(path.split("/")[4])
                if not self.require_admin(conn, payload.get("user_id")): return
                conn.execute("UPDATE violations SET status='resolved' WHERE id=?", (violation_id,))
                conn.commit()
                send_json(self, {"ok": True, "message": "违规记录已处理"})
            else:
                fail(self, "接口不存在", HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            fail(self, str(exc))
        except Exception as exc:
            print("POST error:", repr(exc))
            fail(self, "服务器内部错误", HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            conn.close()

    def api_delete(self, path, query):
        conn = connect_db()
        try:
            match = re.fullmatch(r"/api/reservations/(\d+)", path)
            if not match: return fail(self, "接口不存在", HTTPStatus.NOT_FOUND)
            reservation_id = int(match.group(1))
            user_id = query.get("user_id", [None])[0]
            reservation = conn.execute("SELECT * FROM reservations WHERE id=?", (reservation_id,)).fetchone()
            if not reservation: return fail(self, "预约不存在", HTTPStatus.NOT_FOUND)
            user = get_user(conn, user_id)
            if not user or (user["role"] != "admin" and user["id"] != reservation["user_id"]): return fail(self, "无权取消该预约", HTTPStatus.FORBIDDEN)
            if reservation["status"] not in ("booked",): return fail(self, "当前状态不能取消")
            conn.execute("UPDATE reservations SET status='cancelled' WHERE id=?", (reservation_id,))
            conn.commit()
            send_json(self, {"ok": True, "message": "预约已取消"})
        except Exception as exc:
            print("DELETE error:", repr(exc))
            fail(self, "服务器内部错误", HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            conn.close()

    def create_reservation(self, conn, payload):
        required(payload, ["user_id", "seat_id", "reservation_date", "start_time", "end_time"])
        user = get_user(conn, payload["user_id"])
        if not user: return fail(self, "用户不存在", HTTPStatus.UNAUTHORIZED)
        slot, error = valid_slot(payload["reservation_date"], payload["start_time"], payload["end_time"])
        if error: return fail(self, error)
        seat = conn.execute("SELECT id FROM seats WHERE id=?", (payload["seat_id"],)).fetchone()
        if not seat: return fail(self, "座位不存在", HTTPStatus.NOT_FOUND)
        if conflict(conn, payload["seat_id"], payload["reservation_date"], payload["start_time"], payload["end_time"]):
            return fail(self, "该座位在所选时段已被预约，请选择其他座位", HTTPStatus.CONFLICT)
        try:
            cur = conn.execute("""INSERT INTO reservations(user_id,seat_id,reservation_date,start_time,end_time)
                VALUES (?,?,?,?,?)""", (payload["user_id"], payload["seat_id"], payload["reservation_date"], payload["start_time"], payload["end_time"]))
            conn.commit()
        except sqlite3.IntegrityError:
            return fail(self, "预约重复或数据冲突", HTTPStatus.CONFLICT)
        send_json(self, {"ok": True, "message": "预约成功", "reservation": row_dict(reservation_view(conn, cur.lastrowid))}, HTTPStatus.CREATED)

    def checkin(self, conn, reservation_id, payload):
        reservation = reservation_view(conn, reservation_id)
        user = get_user(conn, payload.get("user_id"))
        if not reservation: return fail(self, "预约不存在", HTTPStatus.NOT_FOUND)
        if not user or (user["role"] != "admin" and user["id"] != reservation["user_id"]): return fail(self, "无权操作该预约", HTTPStatus.FORBIDDEN)
        if reservation["status"] != "booked": return fail(self, "当前预约状态不能签到")
        conn.execute("UPDATE reservations SET status='checked_in', checkin_at=CURRENT_TIMESTAMP WHERE id=?", (reservation_id,))
        conn.commit()
        send_json(self, {"ok": True, "message": "签到成功"})

    def checkout(self, conn, reservation_id, payload):
        reservation = reservation_view(conn, reservation_id)
        user = get_user(conn, payload.get("user_id"))
        if not reservation: return fail(self, "预约不存在", HTTPStatus.NOT_FOUND)
        if not user or (user["role"] != "admin" and user["id"] != reservation["user_id"]): return fail(self, "无权操作该预约", HTTPStatus.FORBIDDEN)
        if reservation["status"] not in ("checked_in", "booked"): return fail(self, "当前预约状态不能结束")
        conn.execute("UPDATE reservations SET status='completed' WHERE id=?", (reservation_id,))
        conn.commit()
        send_json(self, {"ok": True, "message": "本次自习已结束"})

    def recommendations(self, conn, query):
        reservation_date = query.get("date", [date.today().isoformat()])[0]
        start_time = query.get("start", ["09:00"])[0]
        end_time = query.get("end", ["11:00"])[0]
        user = get_user(conn, query.get("user_id", [None])[0])
        preferences = json.loads(user["preferences"] or "{}") if user else {}
        candidates = []
        for seat in conn.execute("SELECT * FROM seats ORDER BY floor,id").fetchall():
            if conflict(conn, seat["id"], reservation_date, start_time, end_time): continue
            score = 50
            reasons = []
            if preferences.get("window") and seat["near_window"]: score += 25; reasons.append("符合靠窗偏好")
            if preferences.get("power") and seat["power"]: score += 20; reasons.append("提供电源")
            if seat["zone"] == "安静区": score += 5; reasons.append("安静区")
            candidates.append({"score": score, "reason": "、".join(reasons) or "当前时段空闲", **row_dict(seat)})
        candidates.sort(key=lambda item: (-item["score"], item["id"]))
        send_json(self, {"ok": True, "recommendations": candidates[:5]})

    def require_admin(self, conn, user_id):
        user = get_user(conn, user_id)
        if not user or user["role"] != "admin":
            fail(self, "需要管理员权限", HTTPStatus.FORBIDDEN)
            return False
        return True

    def admin_stats(self, conn, query):
        if not self.require_admin(conn, query.get("user_id", [None])[0]): return
        today = date.today().isoformat()
        total = conn.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
        today_count = conn.execute("SELECT COUNT(*) FROM reservations WHERE reservation_date=?", (today,)).fetchone()[0]
        checked = conn.execute("SELECT COUNT(*) FROM reservations WHERE status='checked_in'").fetchone()[0]
        open_violations = conn.execute("SELECT COUNT(*) FROM violations WHERE status='open'").fetchone()[0]
        popular = conn.execute("""SELECT s.code, COUNT(*) count FROM reservations r JOIN seats s ON s.id=r.seat_id
            WHERE r.status != 'cancelled' GROUP BY s.id ORDER BY count DESC LIMIT 5""").fetchall()
        by_day = conn.execute("""SELECT reservation_date day, COUNT(*) count FROM reservations
            GROUP BY reservation_date ORDER BY reservation_date DESC LIMIT 7""").fetchall()
        send_json(self, {"ok": True, "stats": {"total": total, "today": today_count, "checked_in": checked, "open_violations": open_violations, "popular": [row_dict(r) for r in popular], "by_day": [row_dict(r) for r in by_day]}})


def run(host="127.0.0.1", port=8000):
    init_db()
    server = ThreadingHTTPServer((host, port), StudyRoomHandler)
    print(f"校园 AI 智能自习室预约系统已启动：http://{host}:{port}")
    print(f"数据库：{DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
