"""Shared player lookup, ordered pagination, caching, and match presentation."""
from concurrent.futures import Future, ThreadPoolExecutor, as_completed, wait
import json
import os
import threading
import time
from urllib.parse import quote, urlencode

from . import app_database
from .app_config import ENDPOINTS, PLATFORM_BY_REGION, ROOT, ROUTING_BY_PLATFORM, setting_int
from .riot_client import ApiError, metric, riot_get

_inflight = {}
_inflight_lock = threading.Lock()
_request_workers = ThreadPoolExecutor(
    max_workers=setting_int("RIOT_MAX_CONCURRENCY", 3, 1, 8),
    thread_name_prefix="riot-lookup",
)


def cached(namespace, parts, ttl, loader, refresh=False):
    key = app_database.cache_key(parts)
    flight_key = (str(app_database.database_path().resolve()), namespace, key)
    if not refresh:
        entry = app_database.cache_get(namespace, key)
        if entry is not None:
            metric("cache_hits")
            return entry["value"]
    with _inflight_lock:
        future = _inflight.get(flight_key)
        owner = future is None
        if owner:
            future = _inflight[flight_key] = Future()
    if not owner:
        metric("cache_waits")
        return future.result()
    try:
        # A previous owner may have finished between the first read and this lock.
        entry = None if refresh else app_database.cache_get(namespace, key)
        if entry is not None:
            metric("cache_hits")
            value = entry["value"]
        else:
            metric("cache_misses")
            value = loader()
            app_database.cache_put(namespace, key, value, ttl)
        future.set_result(value)
        return value
    except Exception as error:
        future.set_exception(error)
        raise
    finally:
        with _inflight_lock:
            _inflight.pop(flight_key, None)


def validate_game(game):
    if game not in ENDPOINTS:
        raise ApiError("Game must be lol or tft.")


def region_codes(region):
    platform = PLATFORM_BY_REGION.get(region)
    if platform is None:
        raise ApiError("Unsupported region.")
    return platform, ROUTING_BY_PLATFORM[platform]


def validate_riot_id(name):
    if not isinstance(name, str) or len(name) > 100 or name.count("#") != 1:
        raise ApiError("Enter a Riot ID in GameName#TagLine format.")
    game_name, tag_line = (part.strip() for part in name.split("#"))
    if not game_name or not tag_line:
        raise ApiError("Enter a Riot ID in GameName#TagLine format.")
    return game_name, tag_line


def get_api_key_info(game):
    validate_game(game)
    source = "LOL_API_KEY" if game == "lol" else "TFT_API_KEY"
    key = os.getenv(source)
    if not key:
        source, key = "RIOT_API_KEY", os.getenv("RIOT_API_KEY")
    if not key:
        raise ApiError("Set RIOT_API_KEY or the game's API key in config.env.", 500)
    return key, source


def get_api_key(game):
    return get_api_key_info(game)[0]


def riot_base(host):
    return f"https://{host}.api.riotgames.com"


def require_dict(payload, *fields):
    if not isinstance(payload, dict) or any(field not in payload for field in fields):
        raise ApiError("Riot API returned incomplete data.", 502)
    return payload


def get_account(game, routing, name, api_key):
    game_name, tag_line = validate_riot_id(name)

    def load_account():
        return require_dict(riot_get(
            f"{riot_base(routing)}/riot/account/v1/accounts/by-riot-id/"
            f"{quote(game_name, safe='')}/{quote(tag_line, safe='')}", api_key,
        ), "puuid")

    account = cached("account", [game, routing, game_name.casefold(), tag_line.casefold()],
                     setting_int("ACCOUNT_TTL_SECONDS", 86400), load_account)
    return {**account,
            "name": f"{account.get('gameName', game_name)}#{account.get('tagLine', tag_line)}"}


def get_profile(game, platform, account, api_key, refresh=False):
    puuid = account["puuid"]

    def load_profile():
        path = ENDPOINTS[game]["summoner"].format(puuid=quote(puuid, safe=""))
        return require_dict(riot_get(riot_base(platform) + path, api_key), "puuid")

    profile = cached("profile", [game, platform, puuid],
                     setting_int("PROFILE_TTL_SECONDS", 300), load_profile, refresh)
    return {**profile, "puuid": puuid, "name": account["name"]}


def get_summoner(game, platform, routing, name, api_key, refresh=False):
    account = get_account(game, routing, name, api_key)
    return get_profile(game, platform, account, api_key, refresh)


def get_ranked(game, platform, puuid, api_key, refresh=False):
    def load_ranked():
        path = ENDPOINTS[game]["ranked"].format(puuid=quote(puuid, safe=""))
        result = riot_get(riot_base(platform) + path, api_key)
        if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
            raise ApiError("Riot API returned invalid ranked data.", 502)
        return result

    return cached("ranked", [game, platform, puuid],
                  setting_int("PROFILE_TTL_SECONDS", 300), load_ranked, refresh)


def get_match_ids(game, routing, puuid, start, count, api_key, as_of):
    path = ENDPOINTS[game]["matches"] + f"/by-puuid/{quote(puuid, safe='')}/ids"
    query = urlencode({"start": start, "count": count, "endTime": as_of})
    result = riot_get(f"{riot_base(routing)}{path}?{query}", api_key)
    if not isinstance(result, list) or any(not isinstance(item, str) for item in result):
        raise ApiError("Riot API returned an invalid match list.", 502)
    return result


def get_match(game, routing, match_id, api_key):
    def load_match():
        result = require_dict(riot_get(
            riot_base(routing) + ENDPOINTS[game]["matches"] + "/" + quote(match_id, safe=""),
            api_key,
        ), "metadata", "info")
        metadata = require_dict(result["metadata"])
        info = require_dict(result["info"], "participants")
        id_field = "matchId" if game == "lol" else "match_id"
        if metadata.get(id_field) != match_id or not isinstance(info["participants"], list):
            raise ApiError("Riot API returned invalid match data.", 502)
        return result

    return cached("match", [game, routing, match_id],
                  setting_int("MATCH_TTL_SECONDS", 2592000), load_match)


def validate_page(start, count, as_of, refresh):
    if type(start) is not int or start < 0:
        raise ApiError("start must be a non-negative integer.")
    if type(count) is not int or not 1 <= count <= 20:
        raise ApiError("count must be an integer between 1 and 20.")
    if as_of is not None and (type(as_of) is not int or not 1 <= as_of <= int(time.time())):
        raise ApiError("asOf must be a Unix timestamp in seconds, no later than now.")
    if start > 0 and as_of is None:
        raise ApiError("asOf from the first page is required when loading more history.")
    if type(refresh) is not bool or (refresh and (start != 0 or as_of is not None)):
        raise ApiError("refresh is only valid on a new first page.")


def fetch_page(game, region, name, start=0, count=10, as_of=None, refresh=False):
    validate_game(game)
    validate_riot_id(name)
    validate_page(start, count, as_of, refresh)
    platform, routing = region_codes(region)
    key = get_api_key(game)
    account = get_account(game, routing, name, key)
    puuid = account["puuid"]
    ttl = setting_int("MATCH_LIST_TTL_SECONDS", 60)

    def load_ids():
        anchor = as_of if as_of is not None else int(time.time())
        return {"asOf": anchor,
                "ids": get_match_ids(game, routing, puuid, start, count + 1, key, anchor)}

    # A reusable head entry retains its original anchor throughout its TTL.
    # Later pages include that anchor, so new matches cannot shift their offsets.
    namespace = "match_head" if as_of is None else "match_page"
    # Profile, rank and match IDs only depend on the account's PUUID. Start them
    # together; slow profile/rank calls need not delay downloading match details.
    # riot_get still applies the shared RIOT_MAX_CONCURRENCY limit to every call.
    profile_future = _request_workers.submit(get_profile, game, platform, account, key, refresh)
    ranked_future = _request_workers.submit(get_ranked, game, platform, puuid, key, refresh)
    futures = [profile_future, ranked_future]
    try:
        page = cached(namespace, [game, routing, puuid, start, count, as_of],
                      ttl, load_ids, refresh)
        # Surface any already-failed lookup before queuing more upstream work.
        for future in futures:
            if future.done():
                future.result()
        selected_ids = page["ids"][:count]
        match_futures = [_request_workers.submit(get_match, game, routing, match_id, key)
                         for match_id in selected_ids]
        futures.extend(match_futures)
        for future in as_completed(futures):
            future.result()
        summoner, ranked = profile_future.result(), ranked_future.result()
        raw_matches = [future.result() for future in match_futures]
    except Exception:
        for future in futures:
            future.cancel()
        # Finish active work before the request ends; no orphaned cache writes.
        wait(futures)
        raise  # A failed page never advances the client's cursor.
    has_more = len(page["ids"]) > count
    return {
        "summoner": summoner, "ranked": ranked, "rawMatches": raw_matches,
        "platform": platform,
        "pagination": {"start": start, "count": count, "asOf": page["asOf"],
                       "nextStart": start + len(selected_ids) if has_more else None,
                       "hasMore": has_more},
    }


def test_riot_connection(game, region):
    validate_game(game)
    api_key, source = get_api_key_info(game)
    platform, routing = region_codes(region)
    riot_get(riot_base(platform) + ENDPOINTS[game]["status"], api_key)
    return {"ok": True, "game": game, "region": region, "platform": platform,
            "routing": routing, "keySource": source, "riotService": f"{game.upper()} platform status"}


def load_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


QUEUE_BY_ID = {queue["queueId"]: queue["description"] or queue["map"]
               for queue in load_json("data/static/queues.json")}
SPELL_IMAGE_BY_KEY = {spell["key"]: spell["image"]["full"]
                      for spell in load_json("data/static/summoner.json")["data"].values()}


def format_duration(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 60}m {seconds % 60}s"


def participant_name(player):
    name = player.get("riotIdGameName")
    if name:
        tag = player.get("riotIdTagline")
        return f"{name}#{tag}" if tag else name
    return player.get("summonerName") or "Unknown"


def format_kda(participant):
    kills = participant.get("kills", 0)
    deaths = participant.get("deaths", 0)
    assists = participant.get("assists", 0)
    ratio = "Perfect KDA" if deaths == 0 else f"{round((kills + assists) / deaths, 1)} KDA"
    return f"{kills} / {deaths} / {assists}", ratio


def team_rows(participants):
    return [
        [
            {
                "champion": str(player.get("championId", "")),
                "name": participant_name(player),
            }
            for player in participants[:5]
        ],
        [
            {
                "champion": str(player.get("championId", "")),
                "name": participant_name(player),
            }
            for player in participants[5:10]
        ],
    ]


def normalize_lol_match(match, puuid):
    info = match["info"]
    participants = info.get("participants", [])
    player = next((item for item in participants if item.get("puuid") == puuid), None)
    if not player:
        raise ApiError("Summoner was not present in a returned match.", status=502)

    kda, ratio = format_kda(player)
    teams = team_rows(participants)

    return {
        "id": match["metadata"]["matchId"],
        "queue": QUEUE_BY_ID.get(info.get("queueId"), f"Queue {info.get('queueId')}"),
        "timestamp": info.get("gameEndTimestamp") or info.get("gameCreation"),
        "duration": format_duration(info.get("gameDuration")),
        "result": "Victory" if player.get("win") else "Defeat",
        "champion": str(player.get("championId", "")),
        "level": player.get("champLevel", 0),
        "kda": kda,
        "ratio": ratio,
        "spells": [
            SPELL_IMAGE_BY_KEY.get(str(player.get("summoner1Id")), ""),
            SPELL_IMAGE_BY_KEY.get(str(player.get("summoner2Id")), ""),
        ],
        "items": [
            str(player.get(f"item{index}", ""))
            for index in range(7)
            if player.get(f"item{index}", 0)
        ],
        "teamA": teams[0],
        "teamB": teams[1],
    }


def normalize_tft_match(match, puuid):
    info = match["info"]
    participants = info.get("participants", [])
    player = next((item for item in participants if item.get("puuid") == puuid), None)
    if not player:
        raise ApiError("Summoner was not present in a returned match.", status=502)

    active_traits = [
        trait
        for trait in player.get("traits", [])
        if trait.get("tier_current", 0) > 0
    ]
    active_traits.sort(key=lambda trait: trait.get("tier_current", 0), reverse=True)

    return {
        "id": match["metadata"]["match_id"],
        "placement": placement_text(player.get("placement", 0)),
        "placementNumber": player.get("placement", 0),
        "queue": f"Queue {info.get('queue_id')}",
        "timestamp": info.get("game_datetime"),
        "units": [
            {
                "champion": unit.get("character_id", "TFT"),
                "name": unit.get("character_id", "Unknown").replace("_", " "),
            }
            for unit in player.get("units", [])[:9]
        ],
        "traits": [
            trait.get("name", "Trait").replace("_", " ")
            for trait in active_traits[:8]
        ],
    }


def placement_text(placement):
    if placement == 1:
        return "1st place"
    if placement == 2:
        return "2nd place"
    if placement == 3:
        return "3rd place"
    if placement > 0:
        return f"{placement}th place"
    return "N/A"



def search(game, region, name, start=0, count=10, as_of=None, refresh=False):
    page = fetch_page(game, region, name, start, count, as_of, refresh)
    summoner = page["summoner"]
    preferred = "RANKED_SOLO_5x5" if game == "lol" else "RANKED_TFT"
    ranked = next((row for row in page["ranked"] if row.get("queueType") == preferred), {})
    normalizer = normalize_lol_match if game == "lol" else normalize_tft_match
    matches = [normalizer(match, summoner["puuid"]) for match in page["rawMatches"]]
    result = {
        "profile": {"name": summoner["name"], "region": region,
                    "level": summoner.get("summonerLevel", 0),
                    "profileIconId": summoner.get("profileIconId", 0),
                    "rank": ranked.get("tier", "N/A"),
                    "rankQueue": ranked.get("queueType", "")},
        "matches": matches, "pagination": page["pagination"],
        "nextStart": page["pagination"]["nextStart"],
    }
    if start == 0:
        app_database.save_search_result(game, page["platform"], region, summoner["puuid"], result)
    return result
