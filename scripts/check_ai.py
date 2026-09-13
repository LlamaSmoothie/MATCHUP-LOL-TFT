"""Optional paid OpenAI smoke test using fictional statistics, never player data."""
import os
import sys

from backend.analysis_service import request_analysis
from backend.match_analysis import match_evidence
from backend.riot_client import ApiError


def main():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        print("Set OPENAI_API_KEY in config.env before running the live AI check.")
        return 1
    sample = match_evidence({"info": {
        "queueId": 450, "mapId": 12, "gameVersion": "16.18.1", "gameDuration": 1200,
        "participants": [{"puuid": "FICTIONAL", "win": True, "kills": 4, "deaths": 2, "assists": 3,
                          "goldEarned": 10000, "totalMinionsKilled": 60, "neutralMinionsKilled": 0,
                          "totalDamageDealtToChampions": 20000, "visionScore": 0,
                          "damageDealtToBuildings": 2000}]}}, "FICTIONAL")
    try:
        request_analysis(sample, os.getenv("OPENAI_MODEL", "gpt-5.6-luna"), key)
    except ApiError as error:
        print(f"AI check failed: {error}")
        return 1
    print("PASS: OpenAI returned valid structured insights for one fictional match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
