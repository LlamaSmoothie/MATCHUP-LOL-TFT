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

    def get(self, path, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request("GET", path, headers=headers or {})
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

    def test_timeline_route_and_live_origin_controls(self):
        with patch("backend.api_server.match_timeline", return_value={"available": False}) as timeline:
            self.assertEqual(200, self.get("/api/match-timeline?game=lol&region=Korea&name=Source%23A&matchId=KR_1")[0])
            timeline.assert_called_once_with(game="lol", region="Korea", name="Source#A", match_id="KR_1")
        with patch("backend.api_server.live_game", return_value={"active": False}) as live:
            for headers, allowed in (({}, True), ({"Origin": "http://localhost:5173"}, True),
                                     ({"Origin": "https://example.com"}, False),
                                     ({"Host": "example.com"}, False),
                                     ({"Sec-Fetch-Site": "cross-site"}, False)):
                self.assertEqual(200, self.get("/api/live-game?game=lol&region=Korea&name=Source%23A", headers)[0])
                live.assert_called_with("lol", "Korea", "Source#A", allow_local=allowed)

    def test_live_player_route_preserves_source_game_and_participant(self):
        with patch("backend.api_server.live_player_profile", return_value={"rank": {"status": "ready"}}) as profile:
            path = "/api/live-player?game=lol&region=Korea&name=Source%23A&gameId=123&participant=2"
            self.assertEqual(200, self.get(path)[0])
            profile.assert_called_once_with("lol", "Korea", "Source#A", "123", 2)
            self.assertEqual(400, self.get(path + "&participant=3")[0])
        with patch("backend.api_server.live_player_profile", side_effect=ApiError("Game changed", 409)):
            self.assertEqual(409, self.get(path)[0])

    def test_match_detail_and_participant_routes_preserve_context_and_status(self):
        query = "game=lol&region=Korea&name=Source%23A&matchId=KR_1"
        with patch("backend.api_server.match_details", return_value={"participants": []}) as detail:
            self.assertEqual(200, self.get("/api/match?" + query)[0])
            detail.assert_called_once_with(game="lol", region="Korea", name="Source#A", match_id="KR_1")
        with patch("backend.api_server.match_player", return_value={"name": "Target#B"}) as player:
            self.assertEqual(200, self.get("/api/match-player?" + query + "&participant=3")[0])
            player.assert_called_once_with(game="lol", region="Korea", name="Source#A", match_id="KR_1", participant=3)
            self.assertEqual(400, self.get("/api/match-player?" + query + "&participant=x")[0])
        with patch("backend.api_server.match_details", side_effect=ApiError("Expired", 409)):
            self.assertEqual(409, self.get("/api/match?" + query)[0])
        with patch("backend.api_server.match_player", side_effect=ApiError("Limited", 429, 4)):
            status, headers, body = self.get("/api/match-player?" + query + "&participant=3")
            self.assertEqual((429, "4", 4), (status, headers["Retry-After"], body["retryAfter"]))


if __name__ == "__main__":
    unittest.main()
