"""Optional paid OpenAI smoke test using fictional statistics, never player data."""
import os
import sys

from backend.analysis_service import request_analysis, summarize_matches
from backend.riot_client import ApiError


def main():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        print("Set OPENAI_API_KEY in config.env before running the live AI check.")
        return 1
    sample = summarize_matches([
        {"champion": "6", "result": "Victory" if index == 0 else "Defeat",
         "queueId": 420, "queue": "Ranked Solo", "role": "TOP", "patch": "16.18",
         "kills": 4, "deaths": 2, "assists": 3, "finalItems": ["1001"], "runes": None}
        for index in range(2)], {"queue": "420", "role": "TOP", "patch": "16.18"})
    try:
        request_analysis(sample, os.getenv("OPENAI_MODEL", "gpt-5.6-luna"), key)
    except ApiError as error:
        print(f"AI check failed: {error}")
        return 1
    print("PASS: OpenAI returned valid structured insights for a fictional two-match sample.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
