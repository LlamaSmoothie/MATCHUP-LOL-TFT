from io import BytesIO
import json
import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from backend import riot_client as client
from backend.riot_client import ApiError


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"RIOT_MAX_RETRIES": "2", "RIOT_TIMEOUT_SECONDS": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        client._cooldowns.clear()
        self.opener = MagicMock()
        mocked = patch("backend.riot_client.build_opener", return_value=self.opener)
        mocked.start()
        self.addCleanup(mocked.stop)
        self.sleep = patch("backend.riot_client.time.sleep").start()
        self.addCleanup(patch.stopall)

    def response(self, value):
        result = MagicMock()
        result.__enter__.return_value.read.return_value = json.dumps(value).encode()
        return result

    def get(self, host="na1"):
        return client.riot_get(f"https://{host}.api.riotgames.com/test", "secret-key")

    def test_429_propagates_retry_after_and_prevents_calls_during_cooldown(self):
        limited = HTTPError("https://na1.api.riotgames.com/test", 429, "",
                            {"Retry-After": "7"}, BytesIO())
        self.opener.open.side_effect = [limited, self.response({"ok": True})]
        with patch("backend.riot_client.time.monotonic", return_value=100):
            with self.assertRaises(ApiError) as first:
                self.get()
            self.assertEqual(7, first.exception.retry_after)
            with self.assertRaises(ApiError) as second:
                self.get()
            self.assertEqual(429, second.exception.status)
            self.assertEqual(1, self.opener.open.call_count)
        with patch("backend.riot_client.time.monotonic", return_value=107):
            self.assertEqual({"ok": True}, self.get())

    def test_transient_server_error_and_network_failure_retry(self):
        for error in (HTTPError("", 503, "", {}, BytesIO()), URLError("offline")):
            with self.subTest(error=error):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = [error, self.response([])]
                self.assertEqual([], self.get())
                self.assertEqual(2, self.opener.open.call_count)

    def test_permanent_errors_are_not_retried(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = HTTPError("", status, "", {}, BytesIO())
                with self.assertRaises(ApiError):
                    self.get()
                self.assertEqual(1, self.opener.open.call_count)

    def test_retries_are_bounded(self):
        self.opener.open.side_effect = URLError("offline")
        with self.assertRaises(ApiError) as caught:
            self.get()
        self.assertEqual(502, caught.exception.status)
        self.assertEqual(3, self.opener.open.call_count)

    def test_key_is_only_in_header(self):
        self.opener.open.return_value = self.response({})
        self.get()
        request = self.opener.open.call_args.args[0]
        self.assertNotIn("secret-key", request.full_url)
        self.assertEqual("secret-key", request.get_header("X-riot-token"))
        self.assertEqual(1, self.opener.open.call_args.kwargs["timeout"])

    def test_invalid_json_is_reported_without_caching_or_retry(self):
        response = self.response({})
        response.__enter__.return_value.read.return_value = b"invalid"
        self.opener.open.return_value = response
        with self.assertRaises(ApiError):
            self.get()
        self.assertEqual(1, self.opener.open.call_count)


if __name__ == "__main__":
    unittest.main()
