"""Allowlisted end-of-game evidence for one player in one cached LoL match."""
import re

from .match_service import QUEUE_BY_ID

ROLES = {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}
OBJECTIVES = ("baron", "dragon", "tower", "inhibitor", "riftHerald", "horde", "atakhan")


def number(value, maximum=10**12):
    # Riot counters are non-negative integers. Missing/malformed is not zero.
    return value if type(value) is int and 0 <= value <= maximum else None


def total(values):
    return sum(values) if values and all(value is not None for value in values) else None


def ratio(numerator, denominator, scale=1):
    return round(numerator / denominator * scale, 2) if numerator is not None and denominator else None


def team_evidence(info, team_id):
    participants = info.get("participants", [])
    if not team_id or not participants or any(not number(p.get("teamId")) for p in participants):
        return None
    roster = [p for p in participants if p["teamId"] == team_id]
    if not roster:
        return None
    teams = info.get("teams") or []
    team = next((t for t in teams if isinstance(t, dict) and t.get("teamId") == team_id), {})
    objectives = team.get("objectives") or {}
    return {
        "participantCount": len(roster),
        **{field: total([number(p.get(field)) for p in roster])
           for field in ("kills", "deaths", "assists", "goldEarned", "totalDamageDealtToChampions")},
        "objectives": {key: number((objectives.get(key) or {}).get("kills")) for key in OBJECTIVES},
    }


def match_evidence(raw, puuid):
    """Never include account identifiers, champion pools, inventories or runes."""
    player = next(p for p in raw["info"]["participants"] if p.get("puuid") == puuid)
    return participant_evidence(raw, player)


def participant_evidence(raw, player):
    info = raw["info"]
    get = lambda field: number(player.get(field))
    version = re.match(r"^(\d{1,3})\.(\d{1,3})(?:\.|$)", str(info.get("gameVersion", "")))
    patch = f"{version[1]}.{version[2]}" if version else "Unknown"
    duration = number(info.get("gameDuration"))
    # Older Match-V5 records used milliseconds for gameDuration.
    if duration and version:
        if tuple(map(int, version.groups())) < (11, 20):
            duration = duration / 1000
    else:
        # Epoch milliseconds exceed the bounds used for gameplay counters.
        start = number(info.get("gameStartTimestamp"), 10**15)
        end = number(info.get("gameEndTimestamp"), 10**15)
        duration = (end - start) / 1000 if start is not None and end is not None and end > start else None
    minutes = duration / 60 if duration else None
    queue_id = number(info.get("queueId"))
    role = next((player.get(key) for key in ("teamPosition", "individualPosition")
                 if player.get(key) in ROLES), "UNKNOWN")
    team_id = number(player.get("teamId"))
    team = team_evidence(info, team_id)
    opposing_ids = sorted({number(p.get("teamId")) for p in info["participants"]
                           if number(p.get("teamId")) and p.get("teamId") != team_id}) if team_id else []
    kills, deaths, assists = get("kills"), get("deaths"), get("assists")
    takedowns = total([kills, assists])
    cs = total([get("totalMinionsKilled"), get("neutralMinionsKilled")])
    damage = get("totalDamageDealtToChampions")
    gold = get("goldEarned")
    return {
        "context": {
            "queueId": queue_id, "queue": QUEUE_BY_ID.get(queue_id, f"Queue {queue_id}"),
            "mapId": number(info.get("mapId")), "patch": patch, "role": role,
            "durationSeconds": duration,
            "result": "Victory" if player.get("win") is True else "Defeat" if player.get("win") is False else "Unknown",
            "earlySurrender": player.get("gameEndedInEarlySurrender")
            if type(player.get("gameEndedInEarlySurrender")) is bool else None,
        },
        "combat": {
            "kills": kills, "deaths": deaths, "assists": assists,
            "kdaRatio": ratio(takedowns, deaths), "deathless": deaths == 0 if deaths is not None else None,
            "damageToChampions": damage, "damagePerMinute": ratio(damage, minutes),
            "killParticipationPercent": ratio(takedowns, team["kills"], 100) if team else None,
            "teamDamageSharePercent": ratio(damage, team["totalDamageDealtToChampions"], 100) if team else None,
        },
        "economy": {
            "goldEarned": gold, "goldSpent": get("goldSpent"), "goldPerMinute": ratio(gold, minutes),
            "teamGoldSharePercent": ratio(gold, team["goldEarned"], 100) if team else None,
            "laneMinions": get("totalMinionsKilled"), "neutralMinions": get("neutralMinionsKilled"),
            "totalCS": cs, "csPerMinute": ratio(cs, minutes),
        },
        "vision": {"score": get("visionScore"), "wardsPlaced": get("wardsPlaced"),
                   "wardsCleared": get("wardsKilled"), "controlWardsPlaced": get("detectorWardsPlaced")},
        "objectives": {"damageToObjectives": get("damageDealtToObjectives"),
                       "damageToBuildings": get("damageDealtToBuildings"),
                       "turretKills": get("turretKills"), "turretTakedowns": get("turretTakedowns"),
                       "objectivesStolen": get("objectivesStolen")},
        "sustain": {"damageTaken": get("totalDamageTaken"), "selfMitigated": get("damageSelfMitigated"),
                    "healing": get("totalHeal"), "healingToTeammates": get("totalHealsOnTeammates"),
                    "shieldingToTeammates": get("totalDamageShieldedOnTeammates"),
                    "crowdControlSeconds": get("timeCCingOthers"), "timeDeadSeconds": get("totalTimeSpentDead")},
        "team": team,
        "opposingTeams": [team_evidence(info, other) for other in opposing_ids],
        "dataScope": "End-of-game totals for one match; no timeline, events, positions or replay data.",
    }
