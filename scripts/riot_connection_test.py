"""Optional live smoke test; offline regression tests never need a Riot key."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.match_service import fetch_page, test_riot_connection
from backend.riot_client import ApiError


def main():
    parser = argparse.ArgumentParser(description="Test the shared Riot service.")
    parser.add_argument("--game", choices=["lol", "tft"], default="lol")
    parser.add_argument("--region", default="North America")
    parser.add_argument("--riot-id", "--summoner", dest="riot_id",
                        help="Optional GameName#TagLine for a real player lookup.")
    args = parser.parse_args()
    try:
        if args.riot_id:
            page = fetch_page(args.game, args.region, args.riot_id, count=20)
            print(f"PASS: {len(page['rawMatches'])} matches; hasMore={page['pagination']['hasMore']}")
            return 0
        result = test_riot_connection(args.game, args.region)
    except ApiError as error:
        print(f"FAIL: {error}")
        return 1
    print(f"PASS: {result['riotService']} ({result['platform']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
