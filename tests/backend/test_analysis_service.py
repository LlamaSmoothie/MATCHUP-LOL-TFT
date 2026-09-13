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


ANSWER = {"summary": "You won this match with 14 takedowns.", "observations": ["You earned 600 gold per minute."],
          "reviewSuggestions": ["What happened before each death?"], "limitations": ["No timeline data."]}


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
        self.payload = {"game": "lol", "region": "North America", "name": "Player#A", "matchId": "NA1_1"}
        self.put("account", ["lol", "americas", "player", "a"], {"puuid": "PRIVATE_PLAYER_ID"})
        self.put("account", ["lol", "americas", "other", "b"], {"puuid": "PRIVATE_OTHER_ID"})
        self.matches = {}
        for number in (1, 2):
            player = {"puuid": "PRIVATE_PLAYER_ID", "riotIdGameName": "PRIVATE_PLAYER_NAME",
                      "championId": 6, "championName": "INJECTED_CHAMPION", "win": number == 1,
                      "kills": 10 if number == 1 else 2, "deaths": 2 if number == 1 else 6,
                      "assists": 4 if number == 1 else 0, "teamId": 100,
                      "teamPosition": "TOP" if number == 1 else "",
                      "goldEarned": 12000, "goldSpent": 11000, "totalMinionsKilled": 160,
                      "neutralMinionsKilled": 20, "totalDamageDealtToChampions": 24000,
                      "visionScore": 18, "wardsPlaced": 7, "wardsKilled": 2,
                      "damageDealtToObjectives": 4000, "turretTakedowns": 3,
                      "totalTimeSpentDead": 60, "item0": 1001, "perks": {"private": "RUNE_DATA"}}
            allies = [{"teamId": 100, "puuid": f"PRIVATE_ALLY_{i}", "kills": i,
                       "deaths": 1, "assists": 2, "goldEarned": 9000,
                       "totalDamageDealtToChampions": i * 1000} for i in range(1, 5)]
            opponents = [{"teamId": 200, "puuid": f"PRIVATE_ENEMY_{i}", "kills": i,
                          "deaths": 2, "assists": 3, "goldEarned": 7000,
                          "totalDamageDealtToChampions": 5000} for i in range(5)]
            opponents[0]["puuid"] = "PRIVATE_OTHER_ID"
            raw = {"metadata": {"matchId": f"NA1_{number}"},
                   "info": {"participants": [*opponents, player, *allies],
                            "queueId": 420 if number == 1 else 450, "mapId": 11 if number == 1 else 12,
                            "gameVersion": "16.18.123", "gameDuration": 1200,
                            "teams": [{"teamId": 100, "objectives": {"dragon": {"kills": 2}, "tower": {"kills": 5}}},
                                      {"teamId": 200, "objectives": {"dragon": {"kills": 1}, "tower": {"kills": 2}}}]}}
            self.matches[number] = raw
            self.put("match", ["lol", "americas", f"NA1_{number}"], raw)

    def put(self, namespace, parts, value):
        db.cache_put(namespace, db.cache_key(parts), value, 999999)

    def test_one_match_uses_requested_player_gameplay_and_correct_team(self):
        evidence, scope = service.load_match(self.payload)
        self.assertEqual((10, 2, 4), tuple(evidence["combat"][k] for k in ("kills", "deaths", "assists")))
        self.assertEqual(7, evidence["combat"]["kdaRatio"])
        self.assertEqual(70, evidence["combat"]["killParticipationPercent"])
        self.assertEqual(70.59, evidence["combat"]["teamDamageSharePercent"])
        self.assertEqual((9, 600, 25), tuple(evidence["economy"][k] for k in ("csPerMinute", "goldPerMinute", "teamGoldSharePercent")))
        self.assertEqual(1200, evidence["combat"]["damagePerMinute"])
        self.assertEqual(18, evidence["vision"]["score"])
        self.assertEqual(4000, evidence["objectives"]["damageToObjectives"])
        self.assertEqual(5, evidence["team"]["participantCount"])
        self.assertEqual(2, evidence["team"]["objectives"]["dragon"])
        self.assertEqual(1, evidence["opposingTeams"][0]["objectives"]["dragon"])
        self.assertEqual("PRIVATE_PLAYER_ID", scope["puuid"])
        other, _ = service.load_match({**self.payload, "name": "Other#B"})
        self.assertEqual(0, other["combat"]["kills"])
        self.assertEqual(1, other["team"]["objectives"]["dragon"])

    def test_provider_input_excludes_identity_and_champion_specific_data(self):
        with patch.object(service, "request_analysis", return_value=ANSWER) as provider:
            result = service.analyze(self.payload)
        evidence = provider.call_args.args[0]
        for private in ("PRIVATE", "NA1_", "Player#", "championId", "championName", "INJECTED", "perks",
                        "RUNE_DATA", "champions", "pickShare", "item0", "filters"):
            self.assertNotIn(private, json.dumps(evidence))
        self.assertEqual("NA1_1", result["matchId"])
        self.assertEqual(evidence, result["match"])
        self.assertNotIn("sample", result)

    def test_aram_is_analyzed_independently_of_champion_filters(self):
        evidence, _ = service.load_match({**self.payload, "matchId": "NA1_2"})
        self.assertEqual((450, "UNKNOWN", "Defeat"), tuple(evidence["context"][k] for k in ("queueId", "role", "result")))
        self.assertIn("ARAM", evidence["context"]["queue"])
        self.assertEqual(2, evidence["combat"]["kills"])
        self.assertIn("In ARAM", service.INSTRUCTIONS)
        self.assertIn("no timeline", evidence["dataScope"])

    def test_missing_raw_data_and_wrong_player_are_rejected(self):
        for fields in ({"name": "Missing#ID"}, {"matchId": "NOT_CACHED"}):
            with self.assertRaises(ApiError) as caught:
                service.load_match({**self.payload, **fields})
            self.assertEqual(409, caught.exception.status)
        self.put("account", ["lol", "americas", "outsider", "c"], {"puuid": "NOT_IN_MATCH"})
        with self.assertRaises(ApiError) as caught:
            service.load_match({**self.payload, "name": "Outsider#C"})
        self.assertEqual(400, caught.exception.status)
        raw = copy.deepcopy(self.matches[1])
        raw["metadata"]["matchId"] = "OTHER"
        self.put("match", ["lol", "americas", "NA1_1"], raw)
        with self.assertRaises(ApiError):
            service.load_match(self.payload)

    def test_invalid_requests_never_reach_provider(self):
        for changes in ({"game": "tft"}, {"name": "invalid"}, {"region": []}, {"matchId": ""},
                        {"matchId": ["NA1_1"]}, {"matchId": "../secret"}, {"matchId": 1},
                        {"filters": {"queue": "420"}}, {"matchIds": ["NA1_1"]}, {"summary": "Ignore instructions"}):
            with patch.object(service, "request_analysis") as provider:
                with self.assertRaises(ApiError):
                    service.analyze({**self.payload, **changes})
                provider.assert_not_called()

    def test_cache_isolated_by_match_player_evidence_model_prompt_and_ttl(self):
        with patch.object(service, "request_analysis", return_value=ANSWER) as provider:
            original = service.analyze(self.payload)
            self.assertEqual(original, service.analyze(dict(self.payload)))
            self.assertEqual(1, provider.call_count)
            for change in ({"matchId": "NA1_2"}, {"name": "Other#B"}):
                service.analyze({**self.payload, **change})
            raw = copy.deepcopy(self.matches[1])
            raw["info"]["participants"][5]["visionScore"] = 99
            self.put("match", ["lol", "americas", "NA1_1"], raw)
            service.analyze(self.payload)
            self.assertEqual(4, provider.call_count)
            with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-5.6-terra"}):
                service.analyze(self.payload)
            with patch.object(service, "PROMPT_VERSION", service.PROMPT_VERSION + 1):
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
                service.analyze({**self.payload, "matchId": "NA1_2"})
            self.assertEqual((429, 10), (caught.exception.status, caught.exception.retry_after))
            self.clock.return_value = 1010
            service.analyze({**self.payload, "matchId": "NA1_2"})
            self.clock.return_value = 1020
            with self.assertRaisesRegex(ApiError, "daily"):
                service.analyze({**self.payload, "name": "Other#B"})
            service.analyze(self.payload)
            self.assertEqual(2, provider.call_count)
            with patch.object(service, "_next_request_at", 0):
                with self.assertRaisesRegex(ApiError, "daily"):
                    service.analyze({**self.payload, "name": "Other#B"})
            self.clock.return_value = 86400
            service.analyze({**self.payload, "name": "Other#B"})
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

    def test_missing_invalid_zero_and_deathless_fields_stay_distinct(self):
        player = {"puuid": "PLAYER"}
        raw = {"info": {"participants": [player]}}
        evidence = service.match_evidence(raw, "PLAYER")
        self.assertIsNone(evidence["combat"]["kills"])
        self.assertIsNone(evidence["combat"]["deathless"])
        self.assertIsNone(evidence["economy"]["csPerMinute"])
        self.assertIsNone(evidence["team"])
        self.assertEqual("Unknown", evidence["context"]["result"])
        player.update(kills=0, deaths=0, assists=0, win=True, goldEarned=0,
                      totalMinionsKilled=0, neutralMinionsKilled=0)
        raw["info"].update(gameDuration=60, gameVersion="16.18.1")
        evidence = service.match_evidence(raw, "PLAYER")
        self.assertTrue(evidence["combat"]["deathless"])
        self.assertIsNone(evidence["combat"]["kdaRatio"])
        self.assertEqual(0, evidence["economy"]["csPerMinute"])
        self.assertEqual(0, evidence["economy"]["goldPerMinute"])
        for invalid in (True, -1, "10", 2.5, 10**13):
            player["kills"] = invalid
            self.assertIsNone(service.match_evidence(raw, "PLAYER")["combat"]["kills"])

    def test_partial_team_metrics_do_not_create_inflated_shares(self):
        raw = copy.deepcopy(self.matches[1])
        raw["info"]["participants"][6].pop("goldEarned")
        evidence = service.match_evidence(raw, "PRIVATE_PLAYER_ID")
        self.assertIsNone(evidence["economy"]["teamGoldSharePercent"])
        raw["info"]["participants"][6].pop("teamId")
        evidence = service.match_evidence(raw, "PRIVATE_PLAYER_ID")
        self.assertIsNone(evidence["team"])
        self.assertIsNone(evidence["combat"]["killParticipationPercent"])
        self.assertEqual(24000, evidence["combat"]["damageToChampions"])

    def test_duration_units_and_missing_denominators(self):
        raw = copy.deepcopy(self.matches[1])
        raw["info"].update(gameDuration=1200000, gameVersion="11.19.1")
        self.assertEqual(9, service.match_evidence(raw, "PRIVATE_PLAYER_ID")["economy"]["csPerMinute"])
        raw["info"].update(gameDuration=0, gameStartTimestamp=1700000000000, gameEndTimestamp=1700001200000)
        self.assertEqual(1200, service.match_evidence(raw, "PRIVATE_PLAYER_ID")["context"]["durationSeconds"])
        raw["info"].update(gameDuration=999, gameVersion="unrecognized")
        self.assertEqual(1200, service.match_evidence(raw, "PRIVATE_PLAYER_ID")["context"]["durationSeconds"])
        raw["info"].pop("gameEndTimestamp")
        self.assertIsNone(service.match_evidence(raw, "PRIVATE_PLAYER_ID")["economy"]["csPerMinute"])
        raw["info"].update(gameDuration=1200, gameVersion="unrecognized")
        self.assertIsNone(service.match_evidence(raw, "PRIVATE_PLAYER_ID")["context"]["durationSeconds"])


class OpenAITransportTests(unittest.TestCase):
    def response(self, **changes):
        return {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(ANSWER)}]}], **changes}

    def test_responses_request_uses_private_header_and_strict_json(self):
        with patch.object(service, "build_opener") as opener:
            opener.return_value.open.return_value = BytesIO(json.dumps(self.response()).encode())
            self.assertEqual(ANSWER, service.request_analysis({"context": {"queueId": 450}}, "gpt-5.6-luna", "secret-key"))
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
