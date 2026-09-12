import copy
import unittest

from backend.match_service import normalize_lol_match


class ChampionNormalizationTests(unittest.TestCase):
    def fixture(self):
        player = {"puuid": "PLAYER", "championId": 6, "championName": "Urgot", "win": True,
                  "kills": 10, "deaths": 2, "assists": 7, "teamPosition": "TOP",
                  **{f"item{i}": value for i, value in enumerate([1001, 3071, 3071, 0, 0, 0, 3340])},
                  "perks": {"styles": [
                      {"description": "subStyle", "style": 8400, "selections": [{"perk": 8444}, {"perk": 8451}]},
                      {"description": "primaryStyle", "style": 8000, "selections": [{"perk": 8005}, {"perk": 9101}]}],
                      "statPerks": {"offense": 5005, "flex": 5008, "defense": 5001}}}
        opponent = {**copy.deepcopy(player), "puuid": "OTHER", "championId": 266,
                    "kills": 1, "deaths": 10, "assists": 0, "win": False, "teamPosition": "JUNGLE"}
        return {"metadata": {"matchId": "NA1_1"}, "info": {
            "queueId": 420, "gameVersion": "16.18.123.456", "participants": [opponent, player]}}

    def test_statistics_belong_to_requested_player_and_exclude_trinket(self):
        match = self.fixture()
        result = normalize_lol_match(match, "PLAYER")
        self.assertEqual((10, 2, 7), tuple(result[k] for k in ("kills", "deaths", "assists")))
        self.assertEqual("6", result["champion"])
        self.assertEqual("Urgot", result["championName"])
        self.assertEqual((420, "TOP", "16.18"), (result["queueId"], result["role"], result["patch"]))
        self.assertEqual(["1001", "3071", "3071"], result["finalItems"])
        self.assertIn("3340", result["items"])  # Existing history inventory stays compatible.
        self.assertEqual({"style": 8000, "perks": [8005, 9101]}, result["runes"]["primary"])
        self.assertNotIn("statPerks", result["runes"])
        other = normalize_lol_match(match, "OTHER")
        self.assertEqual(("266", 1, "Defeat", "JUNGLE"),
                         (other["champion"], other["kills"], other["result"], other["role"]))

    def test_optional_fields_distinguish_unavailable_from_zero(self):
        match = {"metadata": {"matchId": "OLD"}, "info": {"participants": [
            {"puuid": "PLAYER", "championId": 6, "win": False}]}}
        result = normalize_lol_match(match, "PLAYER")
        for field in ("kills", "deaths", "assists", "finalItems", "runes", "queueId"):
            self.assertIsNone(result[field])
        self.assertEqual(("UNKNOWN", "Unknown"), (result["role"], result["patch"]))
        player = match["info"]["participants"][0]
        player.update({"kills": 0, "deaths": 0, "assists": 0, "teamPosition": "",
                       "individualPosition": "UTILITY", "perks": None,
                       **{f"item{i}": 0 for i in range(6)}})
        result = normalize_lol_match(match, "PLAYER")
        self.assertEqual(0, result["kills"])
        self.assertEqual([], result["finalItems"])
        self.assertEqual("UTILITY", result["role"])


if __name__ == "__main__":
    unittest.main()
