import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app_database as db, live_profiles as profiles
from backend.riot_client import ApiError


class LiveProfileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"DATABASE_PATH": str(Path(temp.name) / "cache.sqlite3"),
            "RIOT_API_KEY": "test-key", "LOL_API_KEY": "", "LIVE_PROFILE_TTL_SECONDS": "600",
            "PROFILE_TTL_SECONDS": "300", "ACCOUNT_TTL_SECONDS": "86400", "ACTIVE_GAME_TTL_SECONDS": "15"})
        env.start()
        self.addCleanup(env.stop)
        self.account = {"puuid": "PRIVATE_SOURCE", "gameName": "Source", "tagLine": "A"}
        self.roster = [{"puuid": "PRIVATE_OTHER", "riotId": "Other#B"}, {"puuid": "PRIVATE_SOURCE", "riotId": "Source#A"}]
        db.cache_put("account", db.cache_key(["lol", "americas", "source", "a"]), self.account, 86400)
        self.cache_game()
        self.request = {"game": "lol", "region": "North America", "name": "Source#A", "game_id": "123", "participant": 0}

    def cache_game(self):
        db.cache_put("active_game", db.cache_key(["lol", "na1", "PRIVATE_SOURCE"]),
                     {"raw": {"gameId": 123, "participants": self.roster}}, 60)

    def match(self, champion=6, kills=6, deaths=2, assists=4, **info):
        return {"metadata": {"matchId": "NA1_1"}, "info": {"queueId": 450, "gameType": "MATCHED_GAME", "participants": [
            {"puuid": "PRIVATE_SOURCE", "championId": 1, "kills": 999, "deaths": 0, "assists": 999},
            {"puuid": "PRIVATE_OTHER", "championId": champion, "kills": kills, "deaths": deaths, "assists": assists}], **info}}

    def test_aram_is_included_custom_and_missing_stats_excluded_and_ids_deduplicated(self):
        ids = ["NA1_1", "NA1_2", "NA1_1", "NA1_3", "NA1_4", "NA1_5"]
        matches = {"NA1_1": self.match(), "NA1_2": self.match(kills=0, deaths=0, assists=2),
                   "NA1_3": self.match(champion=266, kills=3, deaths=1, assists=0),
                   "NA1_4": self.match(gameType="CUSTOM_GAME"), "NA1_5": self.match(kills=None)}
        ranked = [{"queueType": "RANKED_FLEX_SR", "tier": "SILVER", "rank": "IV", "leaguePoints": 0},
                  {"queueType": "RANKED_SOLO_5x5", "tier": "GOLD", "rank": "II", "leaguePoints": 32, "puuid": "PRIVATE_OTHER"}]
        with patch.object(profiles, "get_ranked", return_value=ranked) as rank, \
                patch.object(profiles, "get_match_ids", return_value=ids) as listing, \
                patch.object(profiles, "get_match", side_effect=lambda game, routing, mid, key: matches[mid]) as match:
            first = profiles.live_player_profile(**self.request)
            second = profiles.live_player_profile(**self.request)
            self.assertEqual(first, second)
            listing.assert_called_once()
            self.assertEqual(("lol", "americas", "PRIVATE_OTHER", 0, 20, "test-key"), listing.call_args.args[:6])
            self.assertEqual(5, match.call_count)
            rank.assert_called_with("lol", "na1", "PRIVATE_OTHER", "test-key")
        history = first["history"]
        self.assertEqual((3, 5, 20), (history["sampleSize"], history["requestedMatches"], history["sampleLimit"]))
        self.assertEqual({"champion": "6", "games": 2}, history["mostPlayed"])
        self.assertEqual((3, 1, 2, 5), (history["averageKills"], history["averageDeaths"], history["averageAssists"], history["kda"]))
        self.assertEqual(["Solo/Duo", "Flex"], [q["queue"] for q in first["rank"]["queues"]])
        self.assertNotIn("PRIVATE", json.dumps(first))

    def test_unranked_empty_history_and_deathless_sample_are_not_zero_fabrications(self):
        with patch.object(profiles, "get_ranked", return_value=[]), patch.object(profiles, "get_match_ids", return_value=[]):
            data = profiles.live_player_profile(**self.request)
        self.assertEqual("unranked", data["rank"]["queues"][0]["status"])
        self.assertIsNone(data["history"]["averageKills"])
        self.assertIsNone(data["history"]["mostPlayed"])
        self.assertFalse(data["history"]["deathless"])
        with patch.object(profiles, "get_match_ids", return_value=["NA1_1"]), patch.object(profiles, "get_match", return_value=self.match(deaths=0)):
            history = profiles.recent_history("euw1", "europe", "PRIVATE_OTHER", "test-key")
        self.assertTrue(history["deathless"])
        self.assertIsNone(history["kda"])
        self.assertEqual(0, history["averageDeaths"])

    def test_scope_changes_expired_games_bots_and_hidden_players_do_not_trigger_history(self):
        changes = [{"game": "tft"}, {"game_id": "124"}, {"game_id": "../bad"}, {"participant": -1}, {"participant": 64}, {"participant": 2}]
        with patch.object(profiles, "get_ranked") as rank, patch.object(profiles, "get_match_ids") as listing:
            for change in changes:
                with self.subTest(change=change), self.assertRaises(ApiError):
                    profiles.live_player_profile(**{**self.request, **change})
            for field, value in (("bot", True), ("riotId", None), ("puuid", None)):
                original = self.roster[0][field] if field in self.roster[0] else None
                self.roster[0][field] = value
                self.cache_game()
                with self.assertRaises(ApiError): profiles.live_player_profile(**self.request)
                self.roster[0][field] = original
            db.cache_put("active_game", db.cache_key(["lol", "na1", "PRIVATE_SOURCE"]), None, 60)
            with self.assertRaises(ApiError) as caught: profiles.live_player_profile(**self.request)
            self.assertEqual(409, caught.exception.status)
            rank.assert_not_called()
            listing.assert_not_called()

    def test_rate_limit_keeps_rank_and_failed_history_is_retryable(self):
        with patch.object(profiles, "get_ranked", return_value=[]), \
                patch.object(profiles, "get_match_ids", return_value=["NA1_1"]) as listing, \
                patch.object(profiles, "get_match", side_effect=[ApiError("Limited", 429, 12), self.match()]):
            first = profiles.live_player_profile(**self.request)
            self.assertEqual(12, first["retryAfter"])
            self.assertEqual("ready", first["rank"]["status"])
            self.assertEqual("unavailable", first["history"]["status"])
            second = profiles.live_player_profile(**self.request)
            self.assertEqual("ready", second["history"]["status"])
            listing.assert_called_once()
        with patch.object(profiles, "get_ranked", side_effect=ApiError("Limited", 429, 30)), patch.object(profiles, "recent_history") as history:
            data = profiles.live_player_profile(**self.request)
            self.assertEqual("unavailable", data["rank"]["status"])
            self.assertEqual(30, data["retryAfter"])
            history.assert_not_called()

    def test_rank_failure_preserves_history_and_invalid_rank_is_not_unranked(self):
        with patch.object(profiles, "get_ranked", side_effect=ApiError("Rank unavailable", 502)), patch.object(profiles, "get_match_ids", return_value=[]):
            data = profiles.live_player_profile(**self.request)
            self.assertEqual("unavailable", data["rank"]["status"])
            self.assertEqual("ready", data["history"]["status"])
        data = profiles.ranks([{"queueType": "RANKED_SOLO_5x5", "tier": "bad"}])
        self.assertEqual("unavailable", data["queues"][0]["status"])
        self.assertEqual("unranked", data["queues"][1]["status"])

    def test_parallel_profile_limit_returns_retry_after_without_fetching(self):
        with patch.object(profiles, "_slots") as slots, patch.object(profiles, "get_ranked") as rank:
            slots.acquire.return_value = False
            with self.assertRaises(ApiError) as caught: profiles.live_player_profile(**self.request)
            self.assertEqual((429, 5), (caught.exception.status, caught.exception.retry_after))
            rank.assert_not_called()
            slots.release.assert_not_called()

    def test_repeat_profile_uses_rank_and_history_caches_without_riot_calls(self):
        def riot(url, key):
            self.assertEqual("test-key", key)
            if "/league/v4/" in url: return []
            if "/ids?" in url: return ["NA1_1"]
            if url.endswith("/NA1_1"): return self.match()
            self.fail("Unexpected Riot request")
        with patch("backend.match_service.riot_get", side_effect=riot) as upstream:
            first = profiles.live_player_profile(**self.request)
            self.assertEqual(3, upstream.call_count)
            second = profiles.live_player_profile(**self.request)
            self.assertEqual(3, upstream.call_count)
            self.assertEqual(first, second)

    def test_disabling_spectator_cache_reconfirms_game_before_loading_profiles(self):
        with patch.dict(os.environ, {"ACTIVE_GAME_TTL_SECONDS": "0"}), \
                patch.object(profiles, "current_game", return_value={"raw": {"gameId": 123, "participants": self.roster}}) as current, \
                patch.object(profiles, "get_ranked", return_value=[]), patch.object(profiles, "get_match_ids", return_value=[]):
            self.assertEqual("ready", profiles.live_player_profile(**self.request)["history"]["status"])
            current.assert_called_once()
            current.return_value = None
            with self.assertRaises(ApiError) as caught: profiles.live_player_profile(**self.request)
            self.assertEqual(409, caught.exception.status)
