"""Cached historical context for identified players in a confirmed ongoing LoL game."""
from collections import Counter
import threading
import time

from . import app_database as db
from .app_config import setting_int
from .live_service import current_game, full_id
from .match_analysis import number
from .match_service import cached, get_account, get_api_key, get_match, get_match_ids, get_ranked, region_codes
from .riot_client import ApiError

SAMPLE_SIZE = 20
_slots = threading.BoundedSemaphore(2)
TIERS = {"IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"}
QUEUES = {"RANKED_SOLO_5x5": "Solo/Duo", "RANKED_FLEX_SR": "Flex"}


def can_load_profile(player):
    return bool(not player.get("bot") and full_id(player)
                and isinstance(player.get("puuid"), str) and player["puuid"])


def ranks(entries):
    result = []
    for queue, label in QUEUES.items():
        entry = next((row for row in entries if row.get("queueType") == queue), None)
        if entry is None:
            result.append({"queue": label, "status": "unranked"})
        elif (not isinstance(entry.get("tier"), str) or entry["tier"] not in TIERS
              or not isinstance(entry.get("rank"), str) or entry["rank"] not in {"I", "II", "III", "IV"}
              or number(entry.get("leaguePoints")) is None):
            result.append({"queue": label, "status": "unavailable"})
        else:
            result.append({"queue": label, "status": "ranked", "tier": entry["tier"],
                           "division": entry["rank"], "lp": entry["leaguePoints"]})
    return {"status": "ready", "queues": result}


def recent_history(platform, routing, puuid, key):
    def load():
        as_of = int(time.time())
        ids = cached("live_match_ids", ["lol", routing, puuid, SAMPLE_SIZE], 60,
                     lambda: get_match_ids("lol", routing, puuid, 0, SAMPLE_SIZE, key, as_of))
        ids = list(dict.fromkeys(ids))[:SAMPLE_SIZE]
        champions = Counter()
        kills = deaths = assists = eligible = 0
        for match_id in ids:
            raw = get_match("lol", routing, match_id, key)
            info = raw["info"]
            # Custom games are outside this public profile sample.
            if info.get("gameType") == "CUSTOM_GAME":
                continue
            player = next((p for p in info["participants"] if isinstance(p, dict) and p.get("puuid") == puuid), None)
            if player is None:
                continue
            champion = number(player.get("championId"))
            values = [number(player.get(field)) for field in ("kills", "deaths", "assists")]
            if not champion or any(value is None for value in values):
                continue
            eligible += 1
            champions[champion] += 1
            kills += values[0]
            deaths += values[1]
            assists += values[2]
        most = min(champions, key=lambda c: (-champions[c], c)) if champions else None
        return {"status": "ready", "sampleLimit": SAMPLE_SIZE, "requestedMatches": len(ids),
                "sampleSize": eligible, "asOf": as_of,
                "mostPlayed": {"champion": str(most), "games": champions[most]} if most else None,
                "averageKills": round(kills / eligible, 2) if eligible else None,
                "averageDeaths": round(deaths / eligible, 2) if eligible else None,
                "averageAssists": round(assists / eligible, 2) if eligible else None,
                "kda": round((kills + assists) / deaths, 2) if deaths else None,
                "deathless": bool(eligible and deaths == 0)}

    return cached("live_history", ["v1", "lol", platform, routing, puuid, SAMPLE_SIZE],
                  setting_int("LIVE_PROFILE_TTL_SECONDS", 600, 0, 3600), load)


def live_player_profile(game, region, name, game_id, participant):
    if game != "lol":
        raise ApiError("Ongoing player champion and KDA statistics support LoL only.")
    if not isinstance(game_id, str) or not game_id.isascii() or not game_id.isdigit() or len(game_id) > 20:
        raise ApiError("Provide a valid ongoing game ID.")
    if type(participant) is not int or not 0 <= participant < 64:
        raise ApiError("Provide a valid ongoing participant index.")
    platform, routing = region_codes(region)
    key = get_api_key(game)
    account = get_account(game, routing, name, key)
    if setting_int("ACTIVE_GAME_TTL_SECONDS", 15, 0, 60) == 0:
        # Explicitly disabling this cache still permits profile lookup after a fresh confirmation.
        raw = current_game(game, platform, account, key) or {}
    else:
        record = db.cache_get("active_game", db.cache_key([game, platform, account["puuid"]]))
        raw = (record or {}).get("value") or {}
    raw = raw.get("raw") or {}
    players = raw.get("participants", [])
    if str(raw.get("gameId")) != game_id or not any(p.get("puuid") == account["puuid"] for p in players):
        raise ApiError("The ongoing game changed or its status expired. Check ongoing game again.", 409)
    if participant >= len(players) or not can_load_profile(players[participant]):
        raise ApiError("Historical statistics are unavailable for this participant.", 404)
    player = players[participant]
    if not _slots.acquire(blocking=False):
        raise ApiError("Player statistics are busy. Retry shortly.", 429, 5)
    try:
        result = {"game": game, "region": region, "name": name, "gameId": game_id,
                  "participant": participant, "playerName": full_id(player)}
        retry_after = 0
        for field, fetch in (("rank", lambda: ranks(get_ranked(game, platform, player["puuid"], key))),
                             ("history", lambda: recent_history(platform, routing, player["puuid"], key))):
            if retry_after:
                result[field] = {"status": "unavailable", "message": "Riot is rate limiting requests. Retry after the cooldown."}
                continue
            try:
                result[field] = fetch()
            except ApiError as error:
                result[field] = {"status": "unavailable", "message": str(error)}
                if error.status == 429:
                    retry_after = max(1, error.retry_after or 30)
        if retry_after:
            result["retryAfter"] = retry_after
        return result
    finally:
        _slots.release()
