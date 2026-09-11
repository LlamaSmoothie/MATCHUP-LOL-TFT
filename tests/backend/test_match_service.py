import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, unquote, urlparse
from unittest.mock import patch

from backend import app_database as db
from backend import match_service as service
from backend.riot_client import ApiError
from archive.desktop.searchMatch import SearchMatch


class FakeRiot:
    """An independent upstream fixture: unknown endpoint paths fail immediately."""
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()
        self.timestamps = {f"M{i}": 1000 - i for i in range(23)}
        self.failure = None

    def __call__(self, url, key):
        parsed = urlparse(url)
        path = unquote(parsed.path)
        with self.lock:
            self.calls.append(url)
        if self.failure and self.failure in path:
            raise ApiError("Temporary upstream failure.", 502)
        if "/riot/account/v1/accounts/by-riot-id/" in path:
            name, tag = path.split("/")[-2:]
            return {"puuid": "P" + tag, "gameName": name, "tagLine": tag}
        if path.startswith(("/lol/summoner/v4/summoners/by-puuid/",
                            "/tft/summoner/v1/summoners/by-puuid/")):
            return {"puuid": path.split("/")[-1], "profileIconId": 6, "summonerLevel": 50}
        if path.startswith(("/lol/league/v4/entries/by-puuid/", "/tft/league/v1/by-puuid/")):
            return [{"queueType": "RANKED_SOLO_5x5" if path.startswith("/lol") else "RANKED_TFT",
                     "tier": "GOLD"}]
        if path.startswith(("/lol/match/v5/matches/", "/tft/match/v1/matches/")):
            game = "lol" if path.startswith("/lol") else "tft"
            if path.endswith("/ids"):
                query = parse_qs(parsed.query)
                anchor = int(query["endTime"][0])
                start, count = int(query["start"][0]), int(query["count"][0])
                ids = sorted((m for m, stamp in self.timestamps.items() if stamp <= anchor),
                             key=self.timestamps.get, reverse=True)
                return ids[start:start + count]
            match_id = path.split("/")[-1]
            participants = [{"puuid": "P" + tag, "win": tag == "A", "championId": 6,
                             "placement": 1 if tag == "A" else 8,
                             "units": [], "traits": [], "teamId": 100 if tag == "A" else 200}
                            for tag in ["A", "B"]]
            stamp = self.timestamps[match_id] * 1000
            return {"metadata": {"matchId" if game == "lol" else "match_id": match_id},
                    "info": {"participants": participants, "gameEndTimestamp": stamp,
                             "game_datetime": stamp, "gameDuration": 1200}}
        if path in ("/lol/status/v4/platform-data", "/tft/status/v1/platform-data"):
            return {"id": "NA1"}
        raise AssertionError(f"Unexpected upstream endpoint: {url}")

    def count(self, fragment):
        return sum(fragment in url for url in self.calls)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = {"DATABASE_PATH": os.path.join(self.temp.name, "test.sqlite3"),
                    "RIOT_API_KEY": "test-key", "LOL_API_KEY": "", "TFT_API_KEY": "",
                    "MATCH_LIST_TTL_SECONDS": "60", "ACCOUNT_TTL_SECONDS": "86400",
                    "PROFILE_TTL_SECONDS": "300", "MATCH_TTL_SECONDS": "2592000",
                    "CACHE_CLEANUP_INTERVAL_SECONDS": "3600"}
        self.env = patch.dict(os.environ, settings)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.clock = patch("time.time", return_value=2000.0)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.riot = FakeRiot()
        mocked = patch("backend.match_service.riot_get", side_effect=self.riot)
        mocked.start()
        self.addCleanup(mocked.stop)

    def search(self, game="lol", **kwargs):
        return service.search(game, "North America", kwargs.pop("name", "Player#A"), **kwargs)

    def test_repeat_search_and_page_are_fully_cached_for_both_games(self):
        for game in ("lol", "tft"):
            with self.subTest(game=game):
                first = self.search(game)
                calls = len(self.riot.calls)
                self.assertEqual(first, self.search(game))
                self.assertEqual(calls, len(self.riot.calls))
                self.assertEqual(first["profile"]["name"], "Player#A")
                self.assertEqual(first["profile"]["rank"], "GOLD")
                second = self.search(game, start=10, as_of=first["pagination"]["asOf"])
                calls = len(self.riot.calls)
                self.assertEqual(second, self.search(game, start=10, as_of=2000))
                self.assertEqual(calls, len(self.riot.calls))
                self.assertEqual(second["matches"][0]["id"], "M10")

    def test_match_downloads_start_while_profile_and_rank_are_pending(self):
        for game in ("lol", "tft"):
            with self.subTest(game=game):
                profile_started = threading.Event()
                ranked_started = threading.Event()
                match_started = threading.Event()

                def delayed_riot(url, key):
                    if "/summoner/" in url:
                        profile_started.set()
                        self.assertTrue(match_started.wait(5), "Profile blocked match downloads")
                    elif "/league/" in url:
                        ranked_started.set()
                        self.assertTrue(match_started.wait(5), "Rank blocked match downloads")
                    elif "/ids?" in url:
                        self.assertTrue(profile_started.wait(5))
                        self.assertTrue(ranked_started.wait(5))
                    elif "/matches/M" in url:
                        match_started.set()
                    return self.riot(url, key)

                with ThreadPoolExecutor(max_workers=3) as pool:
                    with patch.object(service, "_request_workers", pool), \
                            patch.object(service, "riot_get", side_effect=delayed_riot):
                        page = self.search(game, count=2)
                self.assertEqual(["M0", "M1"], [row["id"] for row in page["matches"]])
                self.assertEqual("Player#A", page["profile"]["name"])
                calls = len(self.riot.calls)
                self.assertEqual(page, self.search(game, count=2))
                self.assertEqual(calls, len(self.riot.calls))

    def test_lookup_pipeline_also_works_with_one_worker(self):
        with ThreadPoolExecutor(max_workers=1) as pool:
            with patch.object(service, "_request_workers", pool):
                page = self.search(count=2)
        self.assertEqual(["M0", "M1"], [row["id"] for row in page["matches"]])

    def test_profile_and_rank_failures_can_be_retried(self):
        for endpoint in ("/summoner/", "/league/"):
            with self.subTest(endpoint=endpoint):
                self.riot.failure = endpoint
                with self.assertRaises(ApiError):
                    self.search(count=2, refresh=True)
                self.riot.failure = None
                self.assertEqual(2, len(self.search(count=2, refresh=True)["matches"]))

    def test_boundaries_and_lookahead_do_not_fetch_extra_details(self):
        for total in (0, 1, 9, 10, 11, 20, 21):
            with self.subTest(total=total):
                self.riot.timestamps = {f"M{i}": 1000 - i for i in range(total)}
                first = self.search(refresh=True)
                self.assertEqual(min(total, 10), len(first["matches"]))
                self.assertEqual(total > 10, first["pagination"]["hasMore"])
                self.assertEqual(10 if total > 10 else None, first["nextStart"])
        # The last lookahead ID is never downloaded until its page is requested.
        self.assertFalse(any(url.endswith("/M10") for url in self.riot.calls))

    def test_new_match_does_not_shift_later_pages_and_refresh_sees_it(self):
        first = self.search()
        self.riot.timestamps["NEW"] = 2001
        with patch("time.time", return_value=2002.0):
            second = self.search(start=10, as_of=first["pagination"]["asOf"])
            self.assertEqual("M10", second["matches"][0]["id"])
            refreshed = self.search(refresh=True)
        self.assertEqual("NEW", refreshed["matches"][0]["id"])
        self.assertEqual(2002, refreshed["pagination"]["asOf"])

    def test_last_and_empty_page_stop(self):
        last = self.search(start=20, as_of=2000)
        empty = self.search(start=30, as_of=2000)
        self.assertEqual(3, len(last["matches"]))
        for page in (last, empty):
            self.assertFalse(page["pagination"]["hasMore"])
            self.assertIsNone(page["pagination"]["nextStart"])

    def test_large_offsets_can_reach_the_end_instead_of_an_arbitrary_cap(self):
        page = self.search(start=10010, as_of=2000)
        self.assertEqual([], page["matches"])
        self.assertFalse(page["pagination"]["hasMore"])

    def test_refresh_reuses_raw_details_but_refreshes_profile_rank_and_ids(self):
        self.search()
        before = list(self.riot.calls)
        self.search(refresh=True)
        new = self.riot.calls[len(before):]
        self.assertEqual(3, len(new))
        self.assertTrue(any("/summoner/" in url for url in new))
        self.assertTrue(any("/league/" in url for url in new))
        self.assertTrue(any("/ids?" in url for url in new))

    def test_expiry_refetches_only_the_expired_layers(self):
        self.search()
        before = len(self.riot.calls)
        with patch("time.time", return_value=2060.0):
            self.search()
        self.assertEqual(before + 1, len(self.riot.calls))
        self.assertIn("/ids?", self.riot.calls[-1])
        with patch("time.time", return_value=2300.0):
            self.search()
        self.assertEqual(before + 4, len(self.riot.calls))

    def test_same_display_name_different_tags_are_isolated_with_shared_raw_match(self):
        first = self.search(name="Player#A")
        details = self.riot.count("/matches/M")
        second = self.search(name="Player#B")
        self.assertEqual("Victory", first["matches"][0]["result"])
        self.assertEqual("Defeat", second["matches"][0]["result"])
        self.assertEqual(details, self.riot.count("/matches/M"))
        self.assertEqual(2, len(db.recent_searches()))
        self.assertEqual({"Player#A", "Player#B"},
                         {row["summonerName"] for row in db.recent_searches()})

    def test_match_failure_is_not_cached_and_retry_recovers(self):
        self.riot.failure = "/M0"
        with self.assertRaises(ApiError):
            self.search(count=1)
        self.riot.failure = None
        self.assertEqual("M0", self.search(count=1)["matches"][0]["id"])
        self.assertEqual(2, self.riot.count("/matches/M0"))

    def test_timestamp_is_raw_and_history_does_not_extend_cache_expiry(self):
        result = self.search()
        self.assertNotIn("age", result["matches"][0])
        self.assertEqual(1000000, result["matches"][0]["timestamp"])
        key = db.cache_key(["lol", "na1", "PA"])
        first = db.cache_get("profile", key)
        with patch("time.time", return_value=2010.0):
            self.search()
            second = db.cache_get("profile", key)
        self.assertEqual(first["expiresAt"], second["expiresAt"])
        self.assertEqual(2010, db.recent_searches()[0]["updatedAt"])

    def test_invalid_inputs_do_not_reach_riot(self):
        invalid = [
            {"name": "NoTag"}, {"name": "Player#"}, {"start": -1},
            {"count": 0}, {"count": 21}, {"start": 1},
            {"as_of": 3000}, {"as_of": 0}, {"refresh": True, "as_of": 2000},
        ]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ApiError):
                self.search(**kwargs)
        self.assertEqual([], self.riot.calls)

    def test_case_and_whitespace_reuse_account_cache(self):
        self.search(name=" Player # A ")
        self.search(name="player#a")
        self.assertEqual(1, self.riot.count("/by-riot-id/"))

    def test_status_is_game_specific_and_not_cached(self):
        for game in ("lol", "tft"):
            result = service.test_riot_connection(game, "North America")
            self.assertTrue(result["ok"])
            self.assertIn(f"/{game}/status/", self.riot.calls[-1])

    def test_legacy_adapter_advances_its_own_cursor(self):
        for game in ("lol", "tft"):
            result = SearchMatch("North America", game, "Player#A")
            self.assertTrue(result.searchComplete)
            self.assertEqual(20, len(result.match_details))
            self.assertTrue(result.hasMore)
            self.assertTrue(result.lol_view_more(999))
            self.assertEqual("M20", result.match_details[0]["metadata"][
                "matchId" if game == "lol" else "match_id"])
            self.assertFalse(result.hasMore)
            self.assertFalse(result.tft_view_more(999))

    def test_merged_platforms(self):
        for name in ("Philippines", "Thailand", "Singapore"):
            self.assertEqual(("sg2", "sea"), service.region_codes(name))

    def test_participant_names_prefer_complete_riot_ids(self):
        self.assertEqual("Player#A", service.participant_name({
            "riotIdGameName": "Player", "riotIdTagline": "A", "summonerName": "old"}))
        self.assertEqual("old", service.participant_name({"summonerName": "old"}))

    def test_concurrent_misses_share_one_loader(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def loader():
            calls.append(1)
            entered.set()
            self.assertTrue(release.wait(5))
            return {"value": 42}
        with ThreadPoolExecutor(max_workers=4) as pool:
            first = pool.submit(service.cached, "test", ["key"], 60, loader)
            self.assertTrue(entered.wait(5))
            rest = [pool.submit(service.cached, "test", ["key"], 60, loader) for _ in range(3)]
            release.set()
            self.assertEqual([{"value": 42}] * 4, [f.result() for f in [first, *rest]])
        self.assertEqual(1, len(calls))

    def test_ttl_null_values_cleanup_and_schema_version(self):
        db.cache_put("test", "null", None, 60)
        self.assertIsNone(db.cache_get("test", "null")["value"])
        with patch("time.time", return_value=2060):
            self.assertIsNone(db.cache_get("test", "null"))
            self.assertEqual(1, db.cleanup_expired(force=True))
        db.cache_put("test", "version", [], 60)
        with patch.object(db, "CACHE_VERSION", 2):
            self.assertIsNone(db.cache_get("test", "version"))

    def test_existing_database_tables_are_preserved(self):
        with db.connect() as connection:
            connection.execute("CREATE TABLE summoner_searches (legacy_value TEXT)")
            connection.execute("INSERT INTO summoner_searches VALUES ('keep')")
        db.init_db()
        self.search()
        with db.connect() as connection:
            self.assertEqual("keep", connection.execute(
                "SELECT legacy_value FROM summoner_searches").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
