import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app_database as db
from backend import match_details as service
from backend.match_service import get_account
from backend.riot_client import ApiError


class MatchDetailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"DATABASE_PATH": str(Path(self.temp.name) / "test.sqlite3"),
                                     "RIOT_API_KEY": "test-key", "LOL_API_KEY": "", "TFT_API_KEY": ""})
        env.start()
        self.addCleanup(env.stop)
        self.players = [
            {"puuid": "PRIVATE_OPPONENT", "riotIdGameName": "OldName", "riotIdTagline": "OLD",
             "teamId": 200, "championId": 266, "win": False, "kills": 2, "deaths": 10, "assists": 1,
             "goldEarned": 8000, "totalDamageDealtToChampions": 5000, "placement": 8, "units": []},
            {"puuid": "PRIVATE_PLAYER", "teamId": 100, "championId": 6, "win": True,
             "kills": 10, "deaths": 2, "assists": 4, "goldEarned": 12000, "totalDamageDealtToChampions": 20000,
             "totalMinionsKilled": 100, "neutralMinionsKilled": 20, "visionScore": 10, "item0": 1001,
             "placement": 1, "level": 9, "gold_left": 0, "last_round": 35, "players_eliminated": 2,
             "total_damage_to_players": 99, "units": [{"character_id": "TFT_Test", "tier": 3}]}]
        for game in ("lol", "tft"):
            db.cache_put("account", db.cache_key([game, "americas", "source", "a"]), {"puuid": "PRIVATE_PLAYER"}, 99999)
            self.put(game, self.raw(game))

    def raw(self, game="lol"):
        return {"metadata": {"matchId" if game == "lol" else "match_id": "NA1_1"},
                "info": {"participants": copy.deepcopy(self.players), "queueId": 450, "queue_id": 1100,
                         "gameDuration": 1200, "gameVersion": "16.18.1", "game_length": 1250.5}}

    def put(self, game, raw):
        db.cache_put("match", db.cache_key([game, "americas", "NA1_1"]), raw, 99999)

    def detail(self, game="lol", name="Source#A", match_id="NA1_1"):
        return service.match_details(game, "North America", name, match_id)

    def profile(self, participant=0, game="lol"):
        return service.match_player(game, "North America", "Source#A", "NA1_1", participant)

    def test_lol_details_include_scoreboard_and_statistics_without_external_calls(self):
        with patch.object(service, "riot_get") as riot:
            data = self.detail()
            riot.assert_not_called()
        self.assertEqual((450, "Victory"), (data["match"]["context"]["queueId"], data["match"]["context"]["result"]))
        self.assertEqual(10, data["match"]["combat"]["kills"])
        self.assertEqual([200, 100], [p["teamId"] for p in data["participants"]])
        self.assertEqual([False, True], [p["isSearchedPlayer"] for p in data["participants"]])
        self.assertEqual("Source#A", data["participants"][1]["name"])
        self.assertEqual("OldName#OLD", data["participants"][0]["name"])
        self.assertEqual(["1001"], data["participants"][1]["items"])
        self.assertNotIn("PRIVATE", json.dumps(data))
        self.assertNotIn("analysis", data)

    def test_tft_details_include_placements_boards_and_profile_targets(self):
        data = self.detail("tft")
        self.assertEqual(1, data["participants"][1]["placement"])
        self.assertEqual(0, data["participants"][1]["goldLeft"])
        self.assertEqual(3, data["participants"][1]["units"][0]["stars"])
        self.assertTrue(data["participants"][1]["canSearch"])
        self.assertNotIn("PRIVATE", json.dumps(data))

    def test_lookup_resolves_current_name_and_warms_normal_search_cache(self):
        account = {"puuid": "PRIVATE_OPPONENT", "gameName": "Current Name", "tagLine": "NEW"}
        with patch.object(service, "riot_get", return_value=account) as riot:
            identity = self.profile()
            self.assertEqual(identity, self.profile())
            riot.assert_called_once_with("https://americas.api.riotgames.com/riot/account/v1/accounts/by-puuid/PRIVATE_OPPONENT", "test-key")
        self.assertEqual({"game": "lol", "region": "North America", "name": "Current Name#NEW"}, identity)
        with patch("backend.match_service.riot_get") as riot:
            self.assertEqual("PRIVATE_OPPONENT", get_account("lol", "americas", identity["name"], "test-key")["puuid"])
            riot.assert_not_called()

    def test_tft_missing_names_resolve_by_puuid_only_after_profile_click(self):
        raw = self.raw("tft")
        raw["info"]["participants"][0].pop("riotIdGameName")
        self.put("tft", raw)
        with patch.object(service, "riot_get", return_value={"puuid": "PRIVATE_OPPONENT", "gameName": "Resolved", "tagLine": "TFT"}) as riot:
            data = self.detail("tft")
            self.assertEqual("Player 1", data["participants"][0]["name"])
            riot.assert_not_called()
            self.assertEqual("Resolved#TFT", self.profile(game="tft")["name"])
            self.assertEqual(1, riot.call_count)

    def test_self_profile_and_missing_puuid_have_explicit_behavior(self):
        with patch.object(service, "riot_get") as riot:
            self.assertEqual("Source#A", self.profile(1)["name"])
            raw = self.raw()
            raw["info"]["participants"][0].pop("puuid")
            self.put("lol", raw)
            self.assertEqual(2, self.detail()["participants"][0]["statistics"]["combat"]["kills"])
            self.assertEqual("OldName#OLD", self.profile()["name"])
            raw["info"]["participants"][0].pop("riotIdTagline")
            self.put("lol", raw)
            self.assertFalse(self.detail()["participants"][0]["canSearch"])
            with self.assertRaises(ApiError) as caught:
                self.profile()
            self.assertEqual(404, caught.exception.status)
            riot.assert_not_called()

    def test_invalid_cache_scope_and_participant_never_reach_riot(self):
        with patch.object(service, "riot_get") as riot:
            for match_id in ("missing", "../bad"):
                with self.assertRaises(ApiError): self.detail(match_id=match_id)
            with self.assertRaises(ApiError): self.detail(name="Unknown#A")
            for index in (-1, 2, None, True, "0"):
                with self.assertRaises(ApiError): self.profile(index)
            raw = self.raw()
            raw["metadata"]["matchId"] = "OTHER"
            self.put("lol", raw)
            with self.assertRaises(ApiError): self.detail()
            riot.assert_not_called()

    def test_profile_errors_and_mismatched_accounts_are_not_cached(self):
        account = {"puuid": "PRIVATE_OPPONENT", "gameName": "Current", "tagLine": "A"}
        with patch.object(service, "riot_get", side_effect=[ApiError("Limited", 429, 5),
                                                            {**account, "puuid": "WRONG"}, account]) as riot:
            with self.assertRaises(ApiError) as caught: self.profile()
            self.assertEqual(5, caught.exception.retry_after)
            with self.assertRaises(ApiError): self.profile()
            self.assertEqual("Current#A", self.profile()["name"])
            self.assertEqual(3, riot.call_count)


if __name__ == "__main__":
    unittest.main()
