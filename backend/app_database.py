"""SQLite cache and independent recent-search history.

Legacy summoner_searches/match_cache tables are preserved. Their player-relative
payloads cannot safely populate the new raw-data cache.
"""
from contextlib import contextmanager
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from .app_config import ROOT, setting_int

CACHE_VERSION = 1
_schema_lock = threading.Lock()
_initialized = set()
_cleanup_times = {}


def database_path():
    return Path(os.getenv("DATABASE_PATH", ROOT / "data" / "tftlol.sqlite3"))


@contextmanager
def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    path = str(database_path().resolve())
    with _schema_lock:
        if path in _initialized and database_path().exists():
            return
        with connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS api_cache (
                    namespace TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    fetched_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY(namespace, cache_key, schema_version)
                );
                CREATE INDEX IF NOT EXISTS idx_api_cache_expiry
                    ON api_cache(expires_at);
                CREATE TABLE IF NOT EXISTS search_history (
                    game TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    puuid TEXT NOT NULL,
                    region TEXT NOT NULL,
                    riot_id TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    searched_at REAL NOT NULL,
                    PRIMARY KEY(game, platform, puuid)
                );
                CREATE INDEX IF NOT EXISTS idx_search_history_time
                    ON search_history(searched_at DESC);
            """)
        _initialized.add(path)


def cache_key(parts):
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def cache_get(namespace, key):
    init_db()
    with connect() as connection:
        row = connection.execute("""
            SELECT payload_json, fetched_at, expires_at FROM api_cache
            WHERE namespace = ? AND cache_key = ? AND schema_version = ?
              AND expires_at > ?
        """, (namespace, key, CACHE_VERSION, time.time())).fetchone()
    if row is None:
        return None
    try:
        return {"value": json.loads(row["payload_json"]),
                "fetchedAt": row["fetched_at"], "expiresAt": row["expires_at"]}
    except (ValueError, TypeError):
        return None


def cache_put(namespace, key, value, ttl):
    init_db()
    now = time.time()
    with connect() as connection:
        connection.execute("""
            INSERT INTO api_cache VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(namespace, cache_key, schema_version) DO UPDATE SET
                payload_json = excluded.payload_json,
                fetched_at = excluded.fetched_at,
                expires_at = excluded.expires_at
        """, (namespace, key, CACHE_VERSION, json.dumps(value), now, now + ttl))
    cleanup_expired()


def cleanup_expired(force=False):
    init_db()
    path = str(database_path().resolve())
    now = time.time()
    interval = setting_int("CACHE_CLEANUP_INTERVAL_SECONDS", 3600, 1)
    with _schema_lock:
        if not force and now - _cleanup_times.get(path, 0) < interval:
            return 0
        with connect() as connection:
            deleted = connection.execute(
                "DELETE FROM api_cache WHERE expires_at <= ? OR schema_version != ?",
                (now, CACHE_VERSION),
            ).rowcount
        _cleanup_times[path] = now
    return deleted


def save_search_result(game, platform, region, puuid, result):
    init_db()
    profile = result["profile"]
    with connect() as connection:
        connection.execute("""
            INSERT INTO search_history VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game, platform, puuid) DO UPDATE SET
                region = excluded.region, riot_id = excluded.riot_id,
                profile_json = excluded.profile_json, searched_at = excluded.searched_at
        """, (game, platform, puuid, region, profile["name"],
              json.dumps(profile), time.time()))


def recent_searches(limit=10):
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50.")
    init_db()
    with connect() as connection:
        rows = connection.execute("""
            SELECT * FROM search_history ORDER BY searched_at DESC LIMIT ?
        """, (limit,)).fetchall()
    return [{"game": row["game"], "region": row["region"],
             "summonerName": row["riot_id"], "profile": json.loads(row["profile_json"]),
             "updatedAt": row["searched_at"]} for row in rows]
