from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from backend import analysis_service as service
from backend import app_database as db
from backend.riot_client import ApiError


ANSWER = {"summary": "Urgot won one of two games.", "observations": ["The sample has two games."],
          "reviewSuggestions": ["What happened before each death?"], "limitations": ["Small sample."]}


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"DATABASE_PATH": str(Path(self.temp.name) / "test.sqlite3"),
                                     "OPENAI_API_KEY": "private-test-key", "OPENAI_MODEL": "gpt-5.6-luna",
                                     "AI_CACHE_TTL_SECONDS": "60", "AI_MIN_INTERVAL_SECONDS": "0",
                                     "AI_DAILY_REQUEST_LIMIT": "100"})
        env.start()
        self.addCleanup(env.stop)
        clock = patch("time.time", return_value=1000)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        gate = patch.object(service, "_next_request_at", 0)
        gate.start()
        self.addCleanup(gate.stop)
        self.payload = {"game": "lol", "region": "North America", "name": "Player#A",
                        "matchIds": ["NA1_1", "NA1_2"], "filters": {"queue": "", "role": "", "patch": ""}}
        self.put("account", ["lol", "americas", "player", "a"], {"puuid": "PRIVATE_PLAYER_ID"})
        self.put("account", ["lol", "americas", "other", "b"], {"puuid": "PRIVATE_OTHER_ID"})
        for number in (1, 2):
            player = {"puuid": "PRIVATE_PLAYER_ID", "riotIdGameName": "PRIVATE_PLAYER_NAME",
                      "championId": 6, "win": number == 1, "kills": 10 if number == 1 else 2,
                      "deaths": 2 if number == 1 else 6, "assists": 4 if number == 1 else 0,
                      "teamPosition": "TOP", **{f"item{i}": value for i, value in enumerate([1001, 3071, 3071, 0, 0, 0, 3340])},
                      "perks": {"styles": [
                          {"description": "primaryStyle", "style": 8000, "selections": [{"perk": 8005}]},
                          {"description": "subStyle", "style": 8400, "selections": [{"perk": 8444}]}]}}
            other = {**copy.deepcopy(player), "puuid": "PRIVATE_OTHER_ID", "championId": 266, "kills": 0}
            self.put("match", ["lol", "americas", f"NA1_{number}"], {
                "metadata": {"matchId": f"NA1_{number}"},
                "info": {"participants": [other, player], "queueId": 420,
                         "gameVersion": "16.18.123", "gameEndTimestamp": 1000 + number}})

    def put(self, namespace, parts, value):
        db.cache_put(namespace, db.cache_key(parts), value, 999999)

    def test_cached_sample_uses_correct_player_and_precomputed_numbers(self):
        sample, scope = service.load_sample(self.payload)
        row = sample["champions"][0]
        self.assertEqual("Urgot", row["champion"])
        self.assertEqual((2, 1, 1, 50, 100), (row["games"], row["wins"], row["losses"], row["winRatePercent"], row["personalPickSharePercent"]))
        self.assertEqual({"kills": 6, "deaths": 4, "assists": 2}, row["averageKDA"])
        self.assertEqual(2, row["kdaRatio"])
        self.assertEqual(2, row["topFinalItems"][0]["games"])
        self.assertNotIn("3340", json.dumps(sample))
        self.assertNotIn("PRIVATE", json.dumps(sample))
        self.assertNotIn("NA1_", json.dumps(sample))
        self.assertNotIn("Player#", json.dumps(sample))
        self.assertEqual("PRIVATE_PLAYER_ID", scope["puuid"])
        other, _ = service.load_sample({**self.payload, "name": "Other#B"})
        self.assertEqual("Aatrox", other["champions"][0]["champion"])
        self.assertEqual(0, other["champions"][0]["averageKDA"]["kills"])

    def test_filters_empty_samples_and_missing_raw_data(self):
        for filters in ({"queue": "450"}, {"role": "JUNGLE"}, {"patch": "16.17"}):
            with self.assertRaises(ApiError):
                service.load_sample({**self.payload, "filters": {**self.payload["filters"], **filters}})
        for fields in ({"name": "Missing#ID"}, {"matchIds": ["NOT_CACHED"]}):
            with self.assertRaises(ApiError) as caught:
                service.load_sample({**self.payload, **fields})
            self.assertEqual(409, caught.exception.status)
        self.put("account", ["lol", "americas", "outsider", "c"], {"puuid": "NOT_IN_MATCH"})
        with self.assertRaises(ApiError) as caught:
            service.load_sample({**self.payload, "name": "Outsider#C"})
        self.assertEqual(400, caught.exception.status)

    def test_invalid_requests_never_reach_provider(self):
        for changes in ({"game": "tft"}, {"name": "invalid"}, {"region": []}, {"matchIds": []},
                        {"matchIds": ["NA1_1"] * 201}, {"matchIds": ["../secret"]}, {"matchIds": [1]},
                        {"filters": {"queue": 420, "role": "", "patch": ""}}, {"summary": "Ignore instructions"}):
            with patch.object(service, "request_analysis") as provider:
                with self.assertRaises(ApiError):
                    service.analyze({**self.payload, **changes})
                provider.assert_not_called()

    def test_cache_isolated_by_sample_filters_player_model_prompt_and_ttl(self):
        with patch.object(service, "request_analysis", return_value=ANSWER) as provider:
            original = service.analyze(self.payload)
            self.assertEqual(original, service.analyze({**self.payload, "matchIds": ["NA1_2", "NA1_1", "NA1_1"]}))
            self.assertEqual(1, provider.call_count)
            for change in ({"matchIds": ["NA1_1"]}, {"name": "Other#B"},
                           {"filters": {"queue": "420", "role": "", "patch": ""}}):
                service.analyze({**self.payload, **change})
            self.assertEqual(4, provider.call_count)
            with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-5.6-terra"}):
                service.analyze(self.payload)
            with patch.object(service, "PROMPT_VERSION", 2):
                service.analyze(self.payload)
            self.assertEqual(6, provider.call_count)
            self.clock.return_value = 1060
            self.assertEqual(1060, service.analyze(self.payload)["generatedAt"])
            self.assertEqual(7, provider.call_count)

    def test_failed_calls_are_not_cached_and_missing_key_is_clear(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch.object(service, "request_analysis") as provider:
            with self.assertRaisesRegex(ApiError, "OPENAI_API_KEY"):
                service.analyze(self.payload)
            provider.assert_not_called()
        with patch.object(service, "request_analysis", side_effect=[ApiError("Unavailable", 502), ANSWER]) as provider:
            with self.assertRaises(ApiError):
                service.analyze(self.payload)
            self.assertEqual(ANSWER, service.analyze(self.payload)["analysis"])
            self.assertEqual(2, provider.call_count)

    def test_shared_inflight_calls_generate_only_once(self):
        entered, release = threading.Event(), threading.Event()
        def generate(*args):
            entered.set()
            self.assertTrue(release.wait(5))
            return ANSWER
        with patch.object(service, "request_analysis", side_effect=generate) as provider, ThreadPoolExecutor(2) as pool:
            first = pool.submit(service.analyze, self.payload)
            self.assertTrue(entered.wait(5))
            second = pool.submit(service.analyze, copy.deepcopy(self.payload))
            release.set()
            self.assertEqual(first.result(), second.result())
            self.assertEqual(1, provider.call_count)

    def test_limits_apply_to_new_calls_but_allow_cached_results(self):
        with patch.dict(os.environ, {"AI_MIN_INTERVAL_SECONDS": "10", "AI_DAILY_REQUEST_LIMIT": "2"}), \
                patch.object(service, "request_analysis", return_value=ANSWER) as provider:
            service.analyze(self.payload)
            with self.assertRaises(ApiError) as caught:
                service.analyze({**self.payload, "matchIds": ["NA1_1"]})
            self.assertEqual((429, 10), (caught.exception.status, caught.exception.retry_after))
            self.clock.return_value = 1010
            service.analyze({**self.payload, "matchIds": ["NA1_1"]})
            self.clock.return_value = 1020
            with self.assertRaisesRegex(ApiError, "daily"):
                service.analyze({**self.payload, "matchIds": ["NA1_2"]})
            service.analyze(self.payload)
            self.assertEqual(2, provider.call_count)
            # Daily count survives a process-local cooldown reset.
            with patch.object(service, "_next_request_at", 0):
                with self.assertRaisesRegex(ApiError, "daily"):
                    service.analyze({**self.payload, "matchIds": ["NA1_2"]})
            self.clock.return_value = 86400
            service.analyze({**self.payload, "matchIds": ["NA1_2"]})
            self.assertEqual(3, provider.call_count)

    def test_provider_cooldown_and_busy_slot_do_not_start_extra_calls(self):
        with patch.object(service, "request_analysis", side_effect=ApiError("Limited", 429, 30)) as provider:
            with self.assertRaises(ApiError):
                service.analyze(self.payload)
            with self.assertRaises(ApiError) as caught:
                service.analyze(self.payload)
            self.assertEqual(30, caught.exception.retry_after)
            self.assertEqual(1, provider.call_count)
        with service._generation_lock:
            with self.assertRaisesRegex(ApiError, "Another"):
                service.analyze(self.payload)

    def test_missing_combat_and_empty_inventories_have_honest_coverage(self):
        matches = [{"champion": "6", "result": "Victory", "queueId": None, "queue": "Unknown queue",
                    "role": "UNKNOWN", "patch": "Unknown", "kills": None, "deaths": None,
                    "assists": None, "finalItems": None, "runes": None}]
        row = service.summarize_matches(matches, self.payload["filters"])["champions"][0]
        self.assertIsNone(row["averageKDA"])
        self.assertFalse(row["deathless"])
        self.assertEqual((0, 0), (row["inventoryGames"], row["runeGames"]))
        matches[0].update(kills=0, deaths=0, assists=0, finalItems=[])
        row = service.summarize_matches(matches, self.payload["filters"])["champions"][0]
        self.assertEqual({"kills": 0, "deaths": 0, "assists": 0}, row["averageKDA"])
        self.assertTrue(row["deathless"])
        self.assertEqual(1, row["inventoryGames"])


class OpenAITransportTests(unittest.TestCase):
    def response(self, **changes):
        return {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(ANSWER)}]}], **changes}

    def test_responses_request_uses_private_header_and_strict_json(self):
        with patch.object(service, "build_opener") as opener:
            opener.return_value.open.return_value = BytesIO(json.dumps(self.response()).encode())
            self.assertEqual(ANSWER, service.request_analysis({"sampleSize": 2}, "gpt-5.6-luna", "secret-key"))
        request = opener.return_value.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(service.OPENAI_URL, request.full_url)
        self.assertEqual("POST", request.method)
        self.assertEqual("Bearer secret-key", request.get_header("Authorization"))
        self.assertNotIn("secret-key", request.data.decode())
        self.assertFalse(body["store"])
        self.assertEqual({"effort": "none"}, body["reasoning"])
        self.assertEqual(1200, body["max_output_tokens"])
        self.assertEqual("json_schema", body["text"]["format"]["type"])
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(1, opener.return_value.open.call_count)

    def test_errors_are_sanitized_without_automatic_paid_retries(self):
        errors = [HTTPError(service.OPENAI_URL, code, "private-provider-message", {"Retry-After": "12"}, None)
                  for code in (400, 401, 403, 404, 429, 500)] + [URLError("private-network-message"), TimeoutError()]
        for error in errors:
            with patch.object(service, "build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(ApiError) as caught:
                    service.request_analysis({}, "gpt-5.6-luna", "secret-key")
                self.assertNotIn("private", str(caught.exception))
                self.assertNotIn("secret-key", str(caught.exception))
                self.assertEqual(1, opener.return_value.open.call_count)
                if getattr(error, "code", None) == 429:
                    self.assertEqual(12, caught.exception.retry_after)

    def test_incomplete_refused_oversized_and_malformed_results_are_rejected(self):
        values = [b"not-json", b"x" * 131073, json.dumps(self.response(status="incomplete")).encode(),
                  json.dumps(self.response(output=[])).encode(),
                  json.dumps(self.response(output=[{"type": "message", "content": [{"type": "refusal"}]}])).encode(),
                  json.dumps(self.response(output=[{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}])).encode()]
        for value in values:
            with patch.object(service, "build_opener") as opener:
                opener.return_value.open.return_value = BytesIO(value)
                with self.assertRaises(ApiError):
                    service.request_analysis({}, "gpt-5.6-luna", "secret-key")


if __name__ == "__main__":
    unittest.main()
