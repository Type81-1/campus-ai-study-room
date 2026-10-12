import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from datetime import date
from urllib.error import HTTPError
from urllib.request import Request, urlopen

TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
TMP.close()
os.environ["STUDY_ROOM_DB"] = TMP.name
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402


class StudyRoomApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.StudyRoomHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        try:
            os.unlink(TMP.name)
        except FileNotFoundError:
            pass

    def request(self, path, payload=None, method=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(self.base + path, data=data, method=method or ("POST" if payload is not None else "GET"), headers={"Content-Type": "application/json"})
        try:
            with urlopen(req) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_login_and_seats(self):
        status, data = self.request("/api/login", {"username": "student001", "password": "123456"})
        self.assertEqual(status, 200)
        self.assertEqual(data["user"]["role"], "student")
        status, data = self.request(f"/api/seats?date={date.today().isoformat()}&start=09:00&end=11:00")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["seats"]), 24)
        self.assertTrue(all("available" in item for item in data["seats"]))

    def test_conflict_and_checkin_flow(self):
        today = date.today().isoformat()
        payload = {"user_id": 1, "seat_id": 1, "reservation_date": today, "start_time": "09:00", "end_time": "11:00"}
        status, data = self.request("/api/reservations", payload)
        self.assertEqual(status, 201)
        reservation_id = data["reservation"]["id"]
        status, data = self.request("/api/reservations", {**payload, "user_id": 2})
        self.assertEqual(status, 409)
        self.assertIn("已被预约", data["message"])
        status, data = self.request(f"/api/reservations/{reservation_id}/checkin", {"user_id": 1})
        self.assertEqual(status, 200)
        status, data = self.request(f"/api/reservations/{reservation_id}/checkout", {"user_id": 1})
        self.assertEqual(status, 200)

    def test_recommendation_and_admin_permission(self):
        today = date.today().isoformat()
        status, data = self.request(f"/api/recommendations?user_id=1&date={today}&start=13:00&end=15:00")
        self.assertEqual(status, 200)
        self.assertGreater(len(data["recommendations"]), 0)
        status, data = self.request("/api/admin/stats?user_id=1")
        self.assertEqual(status, 403)
        status, data = self.request("/api/admin/stats?user_id=3")
        self.assertEqual(status, 200)
        self.assertIn("total", data["stats"])


if __name__ == "__main__":
    unittest.main(verbosity=2)



