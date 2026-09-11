"""Configuration shared by the web API, desktop adapter, and smoke test."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path=ROOT / "config.env"):
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                if name.strip():
                    os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


load_env_file()


def setting_int(name, default, minimum=0, maximum=31_536_000):
    value = int(os.getenv(name, default))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


PLATFORM_BY_REGION = {
    "Brazil": "br1", "EU Nordic & East": "eun1", "EU West": "euw1",
    "Japan": "jp1", "Korea": "kr", "Latin America North": "la1",
    "Latin America South": "la2", "North America": "na1", "Oceania": "oc1",
    "Philippines": "sg2", "Russia": "ru", "Singapore": "sg2",
    "Thailand": "sg2", "Turkey": "tr1", "Taiwan": "tw2", "Vietnam": "vn2",
}
ROUTING_BY_PLATFORM = {
    "br1": "americas", "la1": "americas", "la2": "americas", "na1": "americas",
    "eun1": "europe", "euw1": "europe", "ru": "europe", "tr1": "europe",
    "jp1": "asia", "kr": "asia", "oc1": "sea", "sg2": "sea",
    "tw2": "sea", "vn2": "sea",
}

# Endpoint versions and the TFT league path differ from League of Legends.
ENDPOINTS = {
    "lol": {
        "summoner": "/lol/summoner/v4/summoners/by-puuid/{puuid}",
        "ranked": "/lol/league/v4/entries/by-puuid/{puuid}",
        "matches": "/lol/match/v5/matches",
        "status": "/lol/status/v4/platform-data",
    },
    "tft": {
        "summoner": "/tft/summoner/v1/summoners/by-puuid/{puuid}",
        "ranked": "/tft/league/v1/by-puuid/{puuid}",
        "matches": "/tft/match/v1/matches",
        "status": "/tft/status/v1/platform-data",
    },
}
