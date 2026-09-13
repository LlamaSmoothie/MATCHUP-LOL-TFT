"""Completed LoL timelines, fetched separately from the fast match summary."""
from urllib.parse import quote

from . import app_database as db
from .app_config import setting_int
from .match_analysis import ROLES, number, total
from .match_details import load_cached_match
from .match_service import cached, get_api_key, participant_name, riot_base, riot_get
from .riot_client import ApiError

EVENTS = {"CHAMPION_KILL", "BUILDING_KILL", "ELITE_MONSTER_KILL", "TURRET_PLATE_DESTROYED",
          "ITEM_PURCHASED", "ITEM_SOLD", "ITEM_UNDO", "ITEM_DESTROYED", "SKILL_LEVEL_UP",
          "WARD_PLACED", "WARD_KILL"}
OBJECTS = {"BARON_NASHOR", "DRAGON", "RIFTHERALD", "HORDE", "ATAKHAN", "TOWER_BUILDING",
           "INHIBITOR_BUILDING", "AIR_DRAGON", "EARTH_DRAGON", "FIRE_DRAGON", "WATER_DRAGON",
           "ELDER_DRAGON", "CHEMTECH_DRAGON", "HEXTECH_DRAGON"}


def player_id(raw, puuid, timeline):
    player = next(p for p in raw["info"]["participants"] if p.get("puuid") == puuid)
    pid = number(player.get("participantId"))
    mapping = timeline.get("info", {}).get("participants")
    if isinstance(mapping, list):
        mapped = next((number(p.get("participantId")) for p in mapping
                       if isinstance(p, dict) and p.get("puuid") == puuid), None)
        if not mapped or (pid and pid != mapped):
            raise ApiError("Timeline player information does not match this game.", 502)
        pid = mapped
    if not pid:
        raise ApiError("Player mapping is unavailable for this timeline.", 502)
    return pid


def validate_timeline(value, match_id):
    if not isinstance(value, dict) or not isinstance(value.get("metadata"), dict) or value["metadata"].get("matchId") != match_id:
        raise ApiError("Riot returned a timeline for a different match.", 502)
    frames = value["info"].get("frames") if isinstance(value.get("info"), dict) else None
    if not isinstance(frames, list) or len(frames) > 2000 or any(
            not isinstance(f, dict) or number(f.get("timestamp")) is None
            or not isinstance(f.get("participantFrames"), dict)
            or any(not isinstance(p, dict) for p in f["participantFrames"].values())
            or not isinstance(f.get("events"), list) for f in frames):
        raise ApiError("Riot returned an incomplete timeline.", 502)
    return value


def normalize_timeline(raw, timeline, puuid):
    pid = player_id(raw, puuid, timeline)
    players = raw["info"]["participants"]
    selected = next(p for p in players if p.get("puuid") == puuid)
    teams = {}
    for p in players:
        if number(p.get("teamId")) and number(p.get("participantId")):
            teams.setdefault(p["teamId"], []).append(str(p["participantId"]))
    team_id = number(selected.get("teamId"))
    opponents = [p for p in players if p.get("teamId") != team_id]
    role = selected.get("teamPosition")
    opponent = next((p for p in opponents if role in ROLES and p.get("teamPosition") == role), None)
    opponent_id = number(opponent.get("participantId")) if opponent else None
    samples, events, seen = {}, [], set()
    for frame in timeline["info"]["frames"]:
        frames = frame["participantFrames"]
        current = frames.get(str(pid)) or {}
        other = frames.get(str(opponent_id)) or {}
        team_gold = {tid: total([number((frames.get(i) or {}).get("totalGold")) for i in ids])
                     for tid, ids in teams.items()}
        if any(not number(p.get("teamId")) or not number(p.get("participantId")) for p in players):
            team_gold = {}
        own_gold = team_gold.get(team_id)
        enemy_gold = total([v for tid, v in team_gold.items() if tid != team_id])
        point = {"timestamp": frame["timestamp"], "gold": number(current.get("totalGold")),
                 "xp": number(current.get("xp")), "level": number(current.get("level")),
                 "cs": total([number(current.get("minionsKilled")), number(current.get("jungleMinionsKilled"))]),
                 "opponentGold": number(other.get("totalGold")), "opponentXp": number(other.get("xp")),
                 "opponentCs": total([number(other.get("minionsKilled")), number(other.get("jungleMinionsKilled"))]),
                 "teamGold": own_gold, "opposingTeamGold": enemy_gold,
                 "teamGoldDifference": own_gold - enemy_gold if own_gold is not None and enemy_gold is not None else None}
        samples[frame["timestamp"]] = point
        for event in frame["events"]:
            if (not isinstance(event, dict) or not isinstance(event.get("type"), str)
                    or event["type"] not in EVENTS or number(event.get("timestamp")) is None):
                continue
            kind = event["type"]
            participant = number(event.get("participantId"))
            killer, victim = number(event.get("killerId")), number(event.get("victimId"))
            assisting = event.get("assistingParticipantIds")
            assists = [v for v in assisting if number(v)] if isinstance(assisting, list) else []
            actor = participant or killer or number(event.get("creatorId"))
            # Items, skills and wards concern the searched player; combat/objectives cover the game.
            if kind.startswith(("ITEM_", "SKILL_", "WARD_")) and actor != pid:
                continue
            row = {"type": kind, "timestamp": event["timestamp"], "actorId": actor, "victimId": victim,
                   "involvement": "kill" if killer == pid and kind == "CHAMPION_KILL" else
                   "death" if victim == pid and kind == "CHAMPION_KILL" else
                   "assist" if pid in assists and kind == "CHAMPION_KILL" else
                   "participant" if actor == pid else None,
                   "itemId": number(event.get("itemId")), "beforeId": number(event.get("beforeId")),
                   "afterId": number(event.get("afterId")), "skillSlot": number(event.get("skillSlot")),
                   "objective": next((event[k] for k in ("monsterSubType", "monsterType", "buildingType")
                                      if isinstance(event.get(k), str) and event[k] in OBJECTS), None)}
            fingerprint = repr(sorted(row.items()))
            if kind.startswith("ITEM_") or fingerprint not in seen:
                seen.add(fingerprint)
                events.append(row)
    return {"available": bool(samples), "frameInterval": number(timeline["info"].get("frameInterval")),
            "playerId": pid, "opponentId": opponent_id,
            "participants": [{"id": number(p.get("participantId")), "name": participant_name(p),
                              "champion": str(p.get("championId", ""))} for p in players],
            "samples": sorted(samples.values(), key=lambda p: p["timestamp"]),
            "events": sorted(events, key=lambda e: e["timestamp"])}


def match_timeline(game, region, name, match_id):
    if game != "lol":
        raise ApiError("Completed-match timelines currently support League of Legends.")
    raw, scope = load_cached_match(game, region, name, match_id)

    def fetch():
        data = riot_get(f"{riot_base(scope['routing'])}/lol/match/v5/matches/{quote(match_id, safe='')}/timeline",
                        get_api_key(game))
        validate_timeline(data, match_id)
        player_id(raw, scope["puuid"], data)
        return data

    try:
        data = cached("timeline", [game, scope["routing"], match_id],
                      setting_int("TIMELINE_TTL_SECONDS", 2592000), fetch)
    except ApiError as error:
        if error.status not in (404, 410):
            raise
        return {"game": game, "matchId": match_id, "available": False,
                "message": "Riot has no timeline available for this match.", "samples": [], "events": []}
    return {"game": game, "matchId": match_id, **normalize_timeline(raw, data, scope["puuid"])}


def cached_timeline_evidence(raw, scope):
    """Optional numerical evidence, with no identifiers, names, items, or runes."""
    entry = db.cache_get("timeline", db.cache_key(["lol", scope["routing"], scope["matchId"]]))
    if not entry:
        return {"available": False}
    try:
        timeline = normalize_timeline(raw, validate_timeline(entry["value"], scope["matchId"]), scope["puuid"])
    except ApiError:
        return {"available": False}
    samples = timeline["samples"]
    # Bound model input while preserving actual timestamps, not assumed minute marks.
    stride = max(1, (len(samples) + 19) // 20)
    checkpoints = samples[::stride]
    if samples and checkpoints[-1] != samples[-1]:
        checkpoints.append(samples[-1])
    return {"available": timeline["available"], "frameIntervalMs": timeline["frameInterval"],
            "checkpoints": checkpoints, "events": [
                {"timestamp": e["timestamp"], "type": e["type"], "involvement": e["involvement"],
                 "objective": e["objective"]} for e in timeline["events"]
                if e["type"] in ("CHAMPION_KILL", "BUILDING_KILL", "ELITE_MONSTER_KILL")
                and (e["type"] != "CHAMPION_KILL" or e["involvement"])][:80],
            "eventsLimited": True}
