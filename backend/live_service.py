"""Active-game discovery and verified, local-only League live statistics."""
import errno
import json
import math
import os
import ssl
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .app_config import setting_int
from .match_analysis import number
from .match_service import (QUEUE_BY_ID, cached, get_account, get_api_key,
                            region_codes, riot_base, riot_get, validate_game)
from .riot_client import ApiError

LOCAL_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
CERTIFICATE = Path(__file__).with_name("riotgames.pem")


def scalar(value):
    return round(value, 2) if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**10 else None


def full_id(player):
    if not isinstance(player, dict):
        return None
    value = player.get("riotId")
    if not value:
        name = player.get("riotIdGameName")
        tag = player.get("riotIdTagLine") or player.get("riotIdTagline")
        value = f"{name}#{tag}" if name and tag else None
    # Never match by a bare, potentially ambiguous summoner name.
    if not isinstance(value, str) or len(value) > 100 or value.count("#") != 1:
        return None
    parts = [part.strip() for part in value.split("#")]
    return "#".join(parts) if all(parts) else None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalClientError(ApiError):
    def __init__(self, reason, message):
        super().__init__(message, 502)
        self.reason = reason


def connection_error(error):
    if isinstance(error, ssl.SSLCertVerificationError):
        return LocalClientError("certificate_error", "The local game client's HTTPS certificate could not be verified. Update the bundled Riot certificate; live statistics remain unavailable.")
    if isinstance(error, ssl.SSLError):
        return LocalClientError("tls_error", "The local game client's secure connection failed. Retry after the match finishes loading.")
    if isinstance(error, ConnectionRefusedError) or getattr(error, "errno", None) == errno.ECONNREFUSED or getattr(error, "winerror", None) == 10061:
        return LocalClientError("connection_refused", "The local game client is not accepting live-data connections. Enter the match and finish loading; having only the League launcher open is not enough. Then click Check again.")
    if isinstance(error, TimeoutError):
        return LocalClientError("timeout", "The local game client did not respond in time. Check again once the match has finished loading.")
    return LocalClientError("connection_failed", "The backend could not reach the local game client. Run the backend on the game computer and check that local connections are allowed.")


def read_local_game():
    # Trust only Riot's published root for this connection; never change global SSL settings.
    try:
        context = ssl.create_default_context(cafile=str(CERTIFICATE))
    except (OSError, ssl.SSLError):
        raise LocalClientError("certificate_error", "The bundled Riot certificate could not be loaded. Restore backend/riotgames.pem and restart the backend.") from None
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    request = Request(LOCAL_URL, headers={"Accept": "application/json"})
    try:
        with opener.open(request, timeout=2) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise LocalClientError("invalid_response", "The local game client returned too much data.")
        result = json.loads(raw)
        if not isinstance(result, dict) or not isinstance(result.get("allPlayers"), list) or not isinstance(result.get("gameData"), dict):
            raise LocalClientError("invalid_response", "The local game client returned incomplete data.")
        return result
    except HTTPError as error:
        status = error.code
        error.close()
        if status in (404, 503):
            raise LocalClientError("client_not_ready", "The local client is reachable but live match data is not ready. Finish loading into a LoL match and check again.") from None
        raise LocalClientError("http_error", f"The local game client returned HTTP {status}. Live statistics are unavailable; check again after the match loads.") from None
    except URLError as error:
        raise connection_error(error.reason) from None
    except (TimeoutError, OSError) as error:
        raise connection_error(error) from None
    except (ValueError, UnicodeError):
        raise LocalClientError("invalid_response", "The local game client returned invalid data.") from None


def current_game(game, platform, account, key):
    path = f"/lol/spectator/v5/active-games/by-summoner/{quote(account['puuid'], safe='')}"
    if game == "tft":
        path = f"/lol/spectator/tft/v5/active-games/by-puuid/{quote(account['puuid'], safe='')}"

    def fetch():
        try:
            raw = riot_get(riot_base(platform) + path, key)
        except ApiError as error:
            if error.status == 404:
                return None
            raise
        if (not isinstance(raw, dict) or not number(raw.get("gameId")) or not isinstance(raw.get("participants"), list)
                or any(not isinstance(p, dict) for p in raw["participants"])):
            raise ApiError("Riot returned invalid active-game information.", 502)
        if not any(isinstance(p, dict) and p.get("puuid") == account["puuid"] for p in raw["participants"]):
            raise ApiError("The active game does not contain the searched player.", 502)
        return {"raw": raw, "checkedAt": time.time()}

    # A short TTL covers repeated live refreshes, including genuine no-game responses.
    return cached("active_game", [game, platform, account["puuid"]],
                  setting_int("ACTIVE_GAME_TTL_SECONDS", 15, 0, 60), fetch)


def normalize_local(local, spectator, account):
    if (not isinstance(local, dict) or not isinstance(local.get("allPlayers"), list)
            or not isinstance(local.get("gameData"), dict)
            or any(not isinstance(p, dict) or not isinstance(p.get("scores", {}), dict)
                   or not isinstance(p.get("items", []), list) for p in local["allPlayers"])):
        raise ApiError("The local client returned invalid player statistics.", 502)
    players = [p for p in local["allPlayers"] if isinstance(p, dict)]
    selected = next(p for p in spectator["participants"] if p.get("puuid") == account["puuid"])
    target = (full_id(selected) or account["name"]).casefold()
    local_player = next((p for p in players if (full_id(p) or "").casefold() == target), None)
    # Match the complete named roster and map as well as the target identity. No cross-game mixing.
    expected = {(full_id(p) or "").casefold() for p in spectator["participants"] if not p.get("bot")}
    actual = {(full_id(p) or "").casefold() for p in players if not p.get("isBot")}
    active_name = full_id(local.get("activePlayer") or {})
    if not local_player:
        return {"status": "different_game", "reason": "player_mismatch", "message": "The local client is connected, but the searched Riot ID is not in its match. Search a player from the match running on this computer."}
    if not active_name or active_name.casefold() not in actual:
        return {"status": "different_game", "reason": "active_player_unavailable", "message": "The local client has not identified an active player. Finish loading into the match; replay viewing is not supported."}
    if "" in expected or expected != actual:
        return {"status": "different_game", "reason": "roster_mismatch", "message": "The local client is connected, but its player roster does not match Riot's ongoing-game record. Wait for Riot's game status to update and check again."}
    if local["gameData"].get("mapNumber") != spectator.get("mapId"):
        return {"status": "different_game", "reason": "map_mismatch", "message": "The local client is connected, but its map differs from the searched player's ongoing game."}
    game_time = scalar(local["gameData"].get("gameTime"))
    spectator_time = scalar(spectator.get("gameLength"))
    if game_time is None or (spectator_time is not None and abs(game_time - spectator_time) > 180):
        return {"status": "different_game", "reason": "clock_mismatch", "message": "The local client is connected, but its game clock differs from Riot's ongoing-game record. Wait for Riot's game status to update and check again."}
    container = local.get("events")
    events = container.get("Events", []) if isinstance(container, dict) else []
    if not isinstance(events, list):
        raise ApiError("The local client returned invalid events.", 502)
    if any(isinstance(e, dict) and e.get("EventName") == "GameEnd" for e in events):
        return {"status": "ended", "message": "This game has ended. Refresh match history when Riot has processed it."}
    rows = []
    for p in players:
        scores = p.get("scores") or {}
        rows.append({"name": full_id(p) or "Player", "championName": p.get("championName", "Unknown"),
                     "team": p.get("team", "Unknown"), "level": number(p.get("level")),
                     "isSearchedPlayer": p is local_player,
                     "kills": number(scores.get("kills")), "deaths": number(scores.get("deaths")),
                     "assists": number(scores.get("assists")), "cs": number(scores.get("creepScore")),
                     "vision": scalar(scores.get("wardScore")),
                     "items": [str(i["itemID"]) for i in p.get("items", []) if isinstance(i, dict) and number(i.get("itemID"))]})
    # Only data exposed in normal play; no hidden enemy cooldowns or inferred positions.
    return {"status": "connected", "gameTime": game_time, "players": rows,
            "events": [{"type": e["EventName"], "time": scalar(e.get("EventTime"))}
                       for e in events if isinstance(e, dict) and e.get("EventName") in
                       {"FirstBlood", "ChampionKill", "TurretKilled", "InhibKilled", "DragonKill", "BaronKill", "HeraldKill"}][-12:]}


def live_game(game, region, name, allow_local=False):
    validate_game(game)
    platform, routing = region_codes(region)
    key = get_api_key(game)
    account = get_account(game, routing, name, key)
    result = current_game(game, platform, account, key)
    base = {"game": game, "region": region, "name": name, "checkedAt": time.time()}
    if result is None:
        return {**base, "active": False, "message": "Riot reports no available ongoing game for this player.", "pollAfter": None}
    raw = result["raw"]
    queue = number(raw.get("gameQueueConfigId"))
    players = [{"index": i, "canLoadProfile": bool(game == "lol" and not p.get("bot") and full_id(p) and isinstance(p.get("puuid"), str) and p["puuid"]),
                "name": full_id(p) or (account["name"] if p.get("puuid") == account["puuid"] else "Player"),
                "champion": str(p.get("championId", "")), "teamId": number(p.get("teamId")),
                "isSearchedPlayer": p.get("puuid") == account["puuid"]}
               for i, p in enumerate(raw["participants"]) if isinstance(p, dict)]
    details = {"status": "unavailable", "reason": "client_unavailable", "message": "The local game client is unavailable. Finish loading into the matching LoL game and check again."}
    if game == "tft":
        details = {"status": "unsupported", "message": "Riot provides ongoing TFT game information, but this live statistics feed supports LoL only."}
    elif not allow_local:
        details = {"status": "unavailable", "reason": "local_request_required", "message": "Local live statistics require opening this app through localhost on the backend computer. A remote address only shows the ongoing-game roster."}
    elif os.getenv("LOCAL_LIVE_ENABLED", "1") != "1":
        details = {"status": "unavailable", "reason": "disabled", "message": "Local live statistics are disabled. Set LOCAL_LIVE_ENABLED=1 in the backend configuration and restart the backend."}
    else:
        try:
            local = read_local_game()
            if local is not None:
                details = normalize_local(local, raw, account)
        except ApiError as error:
            details = {"status": "unavailable", "reason": getattr(error, "reason", "invalid_response"), "message": str(error)}
    return {**base, "active": details["status"] != "ended", "gameId": str(raw["gameId"]),
            "queue": QUEUE_BY_ID.get(queue, f"Queue {queue}"), "mapId": number(raw.get("mapId")),
            "gameLength": scalar(raw.get("gameLength")), "participants": players,
            "local": details, "pollAfter": None if details["status"] == "ended" else 5}
