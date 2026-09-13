import copy
import json
import os
import ssl
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from pathlib import Path
from unittest.mock import patch

from backend import app_database as db, timeline_service as timeline, live_service as live
from backend.analysis_service import load_match
from backend.riot_client import ApiError


class GameDataTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"DATABASE_PATH": str(Path(temp.name) / "test.sqlite3"),
            "RIOT_API_KEY": "test-key", "LOL_API_KEY": "", "TFT_API_KEY": "", "LOCAL_LIVE_ENABLED": "1",
            "ACCOUNT_TTL_SECONDS": "86400", "TIMELINE_TTL_SECONDS": "2592000", "ACTIVE_GAME_TTL_SECONDS": "15"})
        env.start()
        self.addCleanup(env.stop)
        self.request = {"game": "lol", "region": "North America", "name": "Source#A", "match_id": "NA1_1"}
        self.account = {"puuid": "PRIVATE_SOURCE", "gameName": "Source", "tagLine": "A"}
        self.raw = {"metadata": {"matchId": "NA1_1"}, "info": {"gameVersion": "16.18.1", "gameDuration": 120,
            "queueId": 420, "participants": [
                {"puuid": "PRIVATE_OTHER", "participantId": 2, "teamId": 200, "teamPosition": "TOP", "championId": 266,
                 "riotIdGameName": "Other", "riotIdTagline": "B"},
                {"puuid": "PRIVATE_SOURCE", "participantId": 1, "teamId": 100, "teamPosition": "TOP", "championId": 6,
                 "riotIdGameName": "Source", "riotIdTagline": "A"}]}}
        self.timeline = {"metadata": {"matchId": "NA1_1"}, "info": {"frameInterval": 60000,
            "participants": [{"participantId": p["participantId"], "puuid": p["puuid"]} for p in self.raw["info"]["participants"]],
            "frames": [self.frame(0, 500, 500), self.frame(60000, 900, 700), self.frame(120000, 1300, 1500)]}}
        self.timeline["info"]["frames"][1]["events"] = [
            {"type": "ITEM_PURCHASED", "timestamp": 50001, "participantId": 1, "itemId": 1001},
            {"type": "ITEM_PURCHASED", "timestamp": 50001, "participantId": 1, "itemId": 1001},
            {"type": "ITEM_PURCHASED", "timestamp": 50002, "participantId": 2, "itemId": 2003},
            {"type": "CHAMPION_KILL", "timestamp": 55555, "killerId": 2, "victimId": 1},
            {"type": "ELITE_MONSTER_KILL", "timestamp": 58000, "killerId": 2, "monsterType": "DRAGON"},
            {"type": "UNKNOWN", "timestamp": 59000, "secret": "PRIVATE"}]
        self.spectator = {"gameId": 2, "gameLength": 60, "mapId": 11, "gameQueueConfigId": 420,
            "observers": {"encryptionKey": "PRIVATE_OBSERVER"}, "participants": [
                {"puuid": "PRIVATE_SOURCE", "riotId": "Source#A", "championId": 6, "teamId": 100},
                {"puuid": "PRIVATE_OTHER", "riotId": "Other#B", "championId": 266, "teamId": 200}]}
        self.local = {"activePlayer": {"riotId": "Source#A"}, "gameData": {"mapNumber": 11, "gameTime": 62.5},
            "events": {"Events": [{"EventName": "ChampionKill", "EventTime": 60}, {"EventName": "Secret", "private": "x"}]},
            "allPlayers": [{"riotId": "Source#A", "team": "ORDER", "championName": "Urgot", "level": 2,
                            "scores": {"kills": 0, "deaths": 1, "assists": 0, "creepScore": 4, "wardScore": 0.5}, "items": [{"itemID": 1001}]},
                           {"riotId": "Other#B", "team": "CHAOS", "championName": "Aatrox", "items": []}]}
        for game in ("lol", "tft"):
            db.cache_put("account", db.cache_key([game, "americas", "source", "a"]), self.account, 86400)
        db.cache_put("match", db.cache_key(["lol", "americas", "NA1_1"]), self.raw, 86400)

    def frame(self, timestamp, own, other):
        return {"timestamp": timestamp, "participantFrames": {
            "1": {"totalGold": own, "xp": own, "minionsKilled": 5, "jungleMinionsKilled": 1, "level": 2},
            "2": {"totalGold": other, "xp": other, "minionsKilled": 2, "jungleMinionsKilled": 0}}, "events": []}

    def get_live(self, game="lol", allow_local=True):
        return live.live_game(game, "North America", "Source#A", allow_local=allow_local)

    def test_timeline_uses_correct_route_cache_and_player_mapping(self):
        with patch.object(timeline, "riot_get", return_value=self.timeline) as riot:
            first = timeline.match_timeline(**self.request)
            self.assertEqual(first, timeline.match_timeline(**self.request))
            riot.assert_called_once_with("https://americas.api.riotgames.com/lol/match/v5/matches/NA1_1/timeline", "test-key")
        self.assertEqual(1, first["playerId"])
        self.assertEqual(2, first["opponentId"])
        self.assertEqual([0, 200, -200], [p["teamGoldDifference"] for p in first["samples"]])
        self.assertEqual(6, first["samples"][1]["cs"])
        self.assertEqual(2, len([e for e in first["events"] if e["type"] == "ITEM_PURCHASED"]))
        self.assertEqual("death", next(e for e in first["events"] if e["type"] == "CHAMPION_KILL")["involvement"])
        self.assertNotIn("PRIVATE", json.dumps(first))

    def test_missing_timeline_and_errors_do_not_poison_cache(self):
        with patch.object(timeline, "riot_get", side_effect=[ApiError("Missing", 404), ApiError("Limited", 429, 10), self.timeline]) as riot:
            self.assertFalse(timeline.match_timeline(**self.request)["available"])
            with self.assertRaises(ApiError) as caught: timeline.match_timeline(**self.request)
            self.assertEqual(10, caught.exception.retry_after)
            self.assertTrue(timeline.match_timeline(**self.request)["available"])
            self.assertEqual(3, riot.call_count)

    def test_wrong_scope_and_malformed_timeline_are_rejected(self):
        with patch.object(timeline, "riot_get") as riot:
            for changes in ({"name": "Unknown#A"}, {"match_id": "../bad"}, {"game": "tft"}):
                with self.assertRaises(ApiError): timeline.match_timeline(**{**self.request, **changes})
            riot.assert_not_called()
        for mutate in (lambda d: d["metadata"].update(matchId="OTHER"),
                       lambda d: d["info"]["participants"][1].update(participantId=9),
                       lambda d: d["info"]["frames"][0].update(participantFrames=None)):
            data = copy.deepcopy(self.timeline)
            mutate(data)
            with patch.object(timeline, "riot_get", return_value=data):
                with self.assertRaises(ApiError): timeline.match_timeline(**self.request)
            self.assertIsNone(db.cache_get("timeline", db.cache_key(["lol", "americas", "NA1_1"])))

    def test_timeline_missing_values_stay_unavailable_and_samples_are_ordered(self):
        self.timeline["info"]["frames"][1]["participantFrames"]["1"].pop("totalGold")
        self.timeline["info"]["frames"].reverse()
        data = timeline.normalize_timeline(self.raw, self.timeline, "PRIVATE_SOURCE")
        self.assertEqual([0, 60000, 120000], [p["timestamp"] for p in data["samples"]])
        self.assertIsNone(data["samples"][1]["gold"])
        self.assertIsNone(data["samples"][1]["teamGoldDifference"])

    def test_analysis_only_reads_cached_timeline_with_no_identifiers_or_items(self):
        request = {"game": "lol", "region": "North America", "name": "Source#A", "matchId": "NA1_1"}
        with patch.object(timeline, "riot_get") as riot:
            before, _ = load_match(request)
            self.assertFalse(before["timeline"]["available"])
            db.cache_put("timeline", db.cache_key(["lol", "americas", "NA1_1"]), self.timeline, 60)
            after, _ = load_match(request)
            riot.assert_not_called()
        evidence = after["timeline"]
        self.assertTrue(evidence["available"])
        self.assertNotIn("no timeline", after["dataScope"])
        self.assertIn("death", json.dumps(evidence))
        for hidden in ("Source", "Other", "PRIVATE", "NA1_1", "ITEM_PURCHASED", "Urgot", "1001"):
            self.assertNotIn(hidden, json.dumps(evidence))

    def test_inactive_game_does_not_read_local_client_and_is_short_cached(self):
        with patch.object(live, "riot_get", side_effect=ApiError("Missing", 404)) as riot, patch.object(live, "read_local_game") as local:
            for _ in range(2):
                data = self.get_live()
                self.assertFalse(data["active"])
                self.assertIsNone(data["pollAfter"])
            self.assertEqual(1, riot.call_count)
            local.assert_not_called()

    def test_active_local_game_is_filtered_and_upstream_status_is_cached(self):
        with patch.object(live, "riot_get", return_value=self.spectator) as riot, patch.object(live, "read_local_game", return_value=self.local) as local:
            first = self.get_live()
            self.get_live()
            riot.assert_called_once_with("https://na1.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/PRIVATE_SOURCE", "test-key")
            self.assertEqual(2, local.call_count)
        self.assertTrue(first["active"])
        self.assertEqual("connected", first["local"]["status"])
        self.assertEqual(0, first["local"]["players"][0]["kills"])
        self.assertEqual(0.5, first["local"]["players"][0]["vision"])
        self.assertEqual(1, len(first["local"]["events"]))
        self.assertNotIn("PRIVATE", json.dumps(first))
        self.assertNotIn("encryptionKey", json.dumps(first))

    def test_remote_disabled_or_tft_requests_never_read_local_client(self):
        with patch.object(live, "riot_get", return_value=self.spectator), patch.object(live, "read_local_game") as local:
            self.assertEqual("local_request_required", self.get_live(allow_local=False)["local"]["reason"])
            with patch.dict(os.environ, {"LOCAL_LIVE_ENABLED": "0"}):
                self.assertEqual("disabled", self.get_live()["local"]["reason"])
            self.assertEqual("unsupported", self.get_live(game="tft")["local"]["status"])
            local.assert_not_called()

    def test_wrong_local_identity_roster_map_clock_or_replay_never_leaks_details(self):
        mutations = (lambda d: d["allPlayers"][0].update(riotId="Source#WRONG"),
                       lambda d: d["allPlayers"][1].update(riotId="Different#B"),
                       lambda d: d["gameData"].update(mapNumber=12),
                       lambda d: d["gameData"].update(gameTime=9999),
                       lambda d: d.update(activePlayer={}))
        for mutate, reason in zip(mutations, ("player_mismatch", "roster_mismatch", "map_mismatch", "clock_mismatch", "active_player_unavailable")):
            data = copy.deepcopy(self.local)
            mutate(data)
            result = live.normalize_local(data, self.spectator, {**self.account, "name": "Source#A"})
            self.assertEqual("different_game", result["status"])
            self.assertEqual(reason, result["reason"])
            self.assertNotIn("players", result)

    def test_game_end_and_client_disconnect_clear_live_statistics(self):
        with patch.object(live, "riot_get", return_value=self.spectator), patch.object(live, "read_local_game", return_value=None):
            self.assertEqual("unavailable", self.get_live()["local"]["status"])
        self.local["events"]["Events"].append({"EventName": "GameEnd"})
        with patch.object(live, "read_local_game", return_value=self.local):
            result = self.get_live()
        self.assertFalse(result["active"])
        self.assertIsNone(result["pollAfter"])
        self.assertNotIn("players", result["local"])

    def test_live_rate_limit_and_invalid_scope_never_probe_local_client(self):
        with patch.object(live, "riot_get", side_effect=ApiError("Limited", 429, 12)), patch.object(live, "read_local_game") as local:
            with self.assertRaises(ApiError) as caught: self.get_live()
            self.assertEqual(12, caught.exception.retry_after)
            local.assert_not_called()
        with patch.object(live, "riot_get", return_value={**self.spectator, "participants": []}):
            with self.assertRaises(ApiError): self.get_live()

    def test_local_transport_uses_fixed_loopback_verified_tls_no_key_and_no_redirects(self):
        ssl.create_default_context(cafile=str(live.CERTIFICATE))  # Validate the bundled public CA.
        with patch.object(live, "build_opener") as factory:
            opener = factory.return_value
            opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(self.local).encode()
            self.assertEqual(self.local, live.read_local_game())
            request = opener.open.call_args.args[0]
            self.assertEqual(live.LOCAL_URL, request.full_url)
            self.assertIsNone(request.get_header("X-riot-token"))
            self.assertEqual(2, opener.open.call_args.kwargs["timeout"])
            self.assertIsNone(live.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_local_transport_failures_explain_the_cause_and_preserve_public_roster(self):
        failures = [
            (URLError(ConnectionRefusedError("PRIVATE")), "connection_refused"),
            (ConnectionRefusedError("PRIVATE"), "connection_refused"),
            (URLError(TimeoutError("PRIVATE")), "timeout"),
            (TimeoutError("PRIVATE"), "timeout"),
            (URLError(ssl.SSLCertVerificationError("PRIVATE")), "certificate_error"),
            (URLError(ssl.SSLError("PRIVATE")), "tls_error"),
            (URLError(OSError("PRIVATE")), "connection_failed"),
            (HTTPError(live.LOCAL_URL, 503, "PRIVATE", {}, None), "client_not_ready"),
            (HTTPError(live.LOCAL_URL, 302, "PRIVATE", {}, None), "http_error"),
        ]
        for error, reason in failures:
            with self.subTest(reason=reason), patch.object(live, "riot_get", return_value=self.spectator), patch.object(live, "build_opener") as factory:
                factory.return_value.open.side_effect = error
                result = self.get_live()
                self.assertTrue(result["active"])
                self.assertEqual(2, len(result["participants"]))
                self.assertEqual("unavailable", result["local"]["status"])
                self.assertEqual(reason, result["local"]["reason"])
                self.assertNotIn("players", result["local"])
                self.assertNotIn("PRIVATE", json.dumps(result))

    def test_missing_certificate_and_invalid_local_json_have_specific_errors(self):
        with patch.object(live.ssl, "create_default_context", side_effect=FileNotFoundError("PRIVATE")):
            with self.assertRaises(live.LocalClientError) as caught:
                live.read_local_game()
            self.assertEqual("certificate_error", caught.exception.reason)
            self.assertNotIn("PRIVATE", str(caught.exception))
        with patch.object(live, "build_opener") as factory:
            factory.return_value.open.return_value.__enter__.return_value.read.return_value = b"not json"
            with self.assertRaises(live.LocalClientError) as caught:
                live.read_local_game()
            self.assertEqual("invalid_response", caught.exception.reason)
