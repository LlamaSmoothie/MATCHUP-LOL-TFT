import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from backend.api_server import ApiHandler
from backend.riot_client import ApiError


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self, path):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    def post(self, body, headers=None, path="/api/analyze"):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request("POST", path, body=body, headers=headers or {"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    def test_analysis_post_validates_body_and_preserves_error_status(self):
        with patch("backend.api_server.analyze", return_value={"analysis": {}}) as analyze:
            self.assertEqual(200, self.post('{"game":"lol"}')[0])
            analyze.assert_called_once_with({"game": "lol"})
            for body, headers, status in (("not-json", None, 400),
                ("{}", {"Content-Type": "text/plain"}, 415),
                ("{}", {"Content-Type": "application/json", "Content-Length": "40000"}, 413),
                ("{}", {"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"}, 403)):
                self.assertEqual(status, self.post(body, headers)[0])
            self.assertEqual(1, analyze.call_count)
            self.assertEqual(404, self.post("{}", path="/unknown")[0])
        with patch("backend.api_server.analyze", side_effect=ApiError("Limited", 429, 10)):
            status, headers, body = self.post("{}")
            self.assertEqual((429, "10", 10), (status, headers["Retry-After"], body["retryAfter"]))
        with patch("backend.api_server.analyze", side_effect=RuntimeError("private-key")), \
                patch("backend.api_server.LOGGER.error") as logger:
            status, _, body = self.post("{}")
            self.assertEqual(500, status)
            self.assertNotIn("private-key", json.dumps(body))
            self.assertNotIn("private-key", str(logger.call_args))

    def test_invalid_parameters_return_json_400(self):
        for query in ("count=abc", "start=-1", "count=0", "count=21", "asOf=abc",
                      "refresh=yes", "count=1&count=2", "name=Player", "game=invalid"):
            with self.subTest(query=query):
                status, headers, body = self.get("/api/search?" + query)
                self.assertEqual(400, status)
                self.assertIn("application/json", headers["Content-Type"])
                self.assertIn("error", body)

    def test_recent_search_limits_are_validated(self):
        for value in ("-1", "0", "51", "abc", ""):
            self.assertEqual(400, self.get("/api/recent-searches?limit=" + value)[0])

    def test_retry_after_reaches_the_browser(self):
        with patch("backend.api_server.search", side_effect=ApiError("Rate limited.", 429, 9)):
            status, headers, body = self.get("/api/search")
        self.assertEqual(429, status)
        self.assertEqual("9", headers["Retry-After"])
        self.assertEqual(9, body["retryAfter"])

    def test_health_unknown_route_and_unexpected_error(self):
        self.assertEqual(200, self.get("/api/health")[0])
        self.assertEqual(404, self.get("/missing")[0])
        with patch("backend.api_server.search", side_effect=RuntimeError("internal secret")), \
                patch("backend.api_server.LOGGER.exception"):
            status, headers, body = self.get("/api/search")
        self.assertEqual(500, status)
        self.assertNotIn("secret", json.dumps(body))
        self.assertEqual("no-store", headers["Cache-Control"])

    def test_pagination_arguments_reach_service(self):
        with patch("backend.api_server.search", return_value={"matches": []}) as search:
            self.assertEqual(200, self.get(
                "/api/search?game=tft&region=Korea&name=Player%23TAG&start=10&count=5&asOf=123")[0])
        search.assert_called_once_with(game="tft", region="Korea", name="Player#TAG",
                                       start=10, count=5, as_of=123, refresh=False)


if __name__ == "__main__":
    unittest.main()
