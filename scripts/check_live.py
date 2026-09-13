"""Check the local LoL feed without Riot requests, keys, or player identities in output."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.live_service import LocalClientError, full_id, read_local_game


def main():
    if os.getenv("LOCAL_LIVE_ENABLED", "1") != "1":
        print("FAIL [disabled]: Set LOCAL_LIVE_ENABLED=1 and restart the backend.")
        return 1
    try:
        data = read_local_game()
    except LocalClientError as error:
        print(f"FAIL [{error.reason}]: {error}")
        return 1
    players = data["allPlayers"]
    identified = sum(bool(full_id(p)) for p in players)
    scored = sum(isinstance(p, dict) and isinstance(p.get("scores"), dict) for p in players)
    print(f"PASS: Local HTTPS feed connected; {len(players)} players, {identified} full Riot IDs, {scored} score records.")
    if not full_id(data.get("activePlayer")):
        print("WAIT: The client has not identified an active player. Finish loading into a match.")
        return 1
    print("This verifies the local feed only. Click Check ongoing game to verify the searched player's match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
