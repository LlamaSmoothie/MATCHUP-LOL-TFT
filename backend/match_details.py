"""On-demand match details and participant profile navigation from cached matches."""
import math
import re
from urllib.parse import quote

from . import app_database as db
from .app_config import setting_int
from .match_analysis import match_evidence, number, participant_evidence
from .match_service import (cached, get_api_key, lol_runes,
                            participant_name, region_codes, riot_base, riot_get,
                            validate_game, validate_riot_id)
from .riot_client import ApiError


def load_cached_match(game, region, name, match_id):
    validate_game(game)
    _, routing = region_codes(region)
    game_name, tag = validate_riot_id(name)
    if not isinstance(match_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", match_id):
        raise ApiError("Provide one valid loaded match ID.")
    entry = db.cache_get("account", db.cache_key([game, routing, game_name.casefold(), tag.casefold()]))
    if not entry or not entry["value"].get("puuid"):
        raise ApiError("The player lookup has expired. Search the player again.", 409)
    puuid = entry["value"]["puuid"]
    entry = db.cache_get("match", db.cache_key([game, routing, match_id]))
    if not entry:
        raise ApiError("This match is no longer cached. Search and load that history again.", 409)
    raw = entry["value"]
    id_field = "matchId" if game == "lol" else "match_id"
    if raw.get("metadata", {}).get(id_field) != match_id or not any(
            p.get("puuid") == puuid for p in raw.get("info", {}).get("participants", [])):
        raise ApiError("This match does not belong to this player.", 400)
    return raw, {"routing": routing, "puuid": puuid, "matchId": match_id}


def riot_id(player):
    name, tag = player.get("riotIdGameName"), player.get("riotIdTagline")
    if not isinstance(name, str) or not isinstance(tag, str):
        return None
    try:
        name, tag = validate_riot_id(f"{name}#{tag}")
    except ApiError:
        return None
    return f"{name}#{tag}"


def participant_identity(player, index, puuid, name):
    selected = player.get("puuid") == puuid
    label = name if selected else participant_name(player)
    return {"index": index, "name": label if label != "Unknown" else f"Player {index + 1}",
            "isSearchedPlayer": selected, "canSearch": bool(player.get("puuid") or riot_id(player))}


def tft_units(player):
    return [{"champion": unit.get("character_id", "TFT"),
             "name": str(unit.get("character_id", "Unknown")).replace("_", " "),
             "stars": number(unit.get("tier"))}
            for unit in player.get("units", [])]


def match_details(game, region, name, match_id):
    raw, scope = load_cached_match(game, region, name, match_id)
    participants = raw["info"]["participants"]
    rows = []
    for index, player in enumerate(participants):
        row = participant_identity(player, index, scope["puuid"], name)
        if game == "lol":
            evidence = participant_evidence(raw, player)
            row.update({"teamId": number(player.get("teamId")), "champion": str(player.get("championId", "")),
                        "championName": player.get("championName", ""),
                        "result": "Victory" if player.get("win") is True else "Defeat" if player.get("win") is False else "Unknown",
                        "role": evidence["context"]["role"],
                        "statistics": {key: evidence[key] for key in ("combat", "economy", "vision")},
                        "items": [str(player[f"item{i}"]) for i in range(7) if number(player.get(f"item{i}"))],
                        "runes": lol_runes(player)})
        else:
            row.update({"placement": number(player.get("placement")), "level": number(player.get("level")),
                        "goldLeft": number(player.get("gold_left")), "lastRound": number(player.get("last_round")),
                        "playersEliminated": number(player.get("players_eliminated")),
                        "damageToPlayers": number(player.get("total_damage_to_players")), "units": tft_units(player)})
        rows.append(row)
    if game == "lol":
        match = match_evidence(raw, scope["puuid"])
        timestamp = raw["info"].get("gameEndTimestamp") or raw["info"].get("gameCreation")
    else:
        info = raw["info"]
        duration = info.get("game_length")
        match = {"context": {"queue": f"Queue {info.get('queue_id')}",
                             "durationSeconds": round(duration) if type(duration) in (int, float)
                             and math.isfinite(duration) and duration >= 0 else None}}
        timestamp = info.get("game_datetime")
    return {"game": game, "matchId": match_id, "timestamp": timestamp, "match": match,
            "participants": rows, "playerName": name}


def match_player(game, region, name, match_id, participant):
    raw, scope = load_cached_match(game, region, name, match_id)
    players = raw["info"]["participants"]
    if type(participant) is not int or not 0 <= participant < len(players):
        raise ApiError("Select a participant from this match.")
    player = players[participant]
    puuid = player.get("puuid")
    if puuid == scope["puuid"]:
        return {"game": game, "region": region, "name": name}
    if not puuid:
        full_name = riot_id(player)
        if not full_name:
            raise ApiError("This participant's profile is unavailable in the match record.", 404)
        return {"game": game, "region": region, "name": full_name}

    def resolve():
        account = riot_get(f"{riot_base(scope['routing'])}/riot/account/v1/accounts/by-puuid/{quote(puuid, safe='')}",
                           get_api_key(game))
        if not isinstance(account, dict) or account.get("puuid") != puuid:
            raise ApiError("Riot could not resolve this participant's profile.", 502)
        game_name, tag = account.get("gameName"), account.get("tagLine")
        if not isinstance(game_name, str) or not isinstance(tag, str):
            raise ApiError("Riot has no full Riot ID for this participant.", 404)
        try:
            game_name, tag = validate_riot_id(f"{game_name}#{tag}")
        except ApiError:
            raise ApiError("Riot has no full Riot ID for this participant.", 404) from None
        return {"puuid": puuid, "gameName": game_name, "tagLine": tag}

    ttl = setting_int("ACCOUNT_TTL_SECONDS", 86400)
    account = cached("account_puuid", [game, scope["routing"], puuid], ttl, resolve)
    db.cache_put("account", db.cache_key([game, scope["routing"], account["gameName"].casefold(),
                                        account["tagLine"].casefold()]), account, ttl)
    return {"game": game, "region": region, "name": f"{account['gameName']}#{account['tagLine']}"}
