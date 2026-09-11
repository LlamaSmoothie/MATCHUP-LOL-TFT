"""Riot transport with bounded concurrency, retries and shared cooldown."""
import hashlib
import json
import logging
import math
import threading
import time
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener

from .app_config import setting_int

LOGGER = logging.getLogger(__name__)
_metrics = Counter()
_lock = threading.Lock()
_cooldowns = {}
_slots = threading.BoundedSemaphore(setting_int("RIOT_MAX_CONCURRENCY", 3, 1, 8))


class ApiError(Exception):
    def __init__(self, message, status=400, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def metric(name):
    with _lock:
        _metrics[name] += 1


def metrics_snapshot():
    with _lock:
        return dict(_metrics)


def riot_get(url, api_key):
    # No credentials in URLs or logs; the fingerprint is internal to the limiter.
    scope = (hashlib.sha256(api_key.encode()).digest(), urlparse(url).hostname)
    request = Request(url, headers={"X-Riot-Token": api_key,
                                   "Accept": "application/json", "User-Agent": "TFTLOL/0.2"})
    retries = setting_int("RIOT_MAX_RETRIES", 2, 0, 3)
    timeout = setting_int("RIOT_TIMEOUT_SECONDS", 15, 1, 30)
    for attempt in range(retries + 1):
        started = time.monotonic()
        try:
            with _slots:
                with _lock:
                    remaining = _cooldowns.get(scope, 0) - time.monotonic()
                if remaining > 0:
                    raise ApiError("Riot API rate limit reached. Try again later.",
                                   429, math.ceil(remaining))
                metric("upstream_calls")
                try:
                    with build_opener().open(request, timeout=timeout) as response:
                        return json.loads(response.read().decode("utf-8"))
                except HTTPError as error:
                    status = error.code
                    if status == 429:
                        try:
                            delay = max(1, int(error.headers.get("Retry-After", "1")))
                        except (TypeError, ValueError):
                            delay = 1
                        with _lock:
                            _cooldowns[scope] = max(_cooldowns.get(scope, 0),
                                                    time.monotonic() + delay)
                        metric("rate_limits")
                    error.close()
                    if status == 429:
                        raise ApiError("Riot API rate limit reached. Try again later.", 429, delay)
                    if status in (401, 403):
                        raise ApiError("Riot API key was rejected or has expired.", 502)
                    if status == 404:
                        raise ApiError("Player or match data was not found.", 404)
                    if status < 500 or attempt == retries:
                        raise ApiError(f"Riot API returned HTTP {status}.", 502)
        except (URLError, TimeoutError, OSError):
            if attempt == retries:
                raise ApiError("Could not reach Riot API. Try again later.", 502) from None
        except (ValueError, UnicodeError):
            raise ApiError("Riot API returned an invalid response.", 502) from None
        finally:
            LOGGER.info("riot_request host=%s duration_ms=%.0f attempt=%s",
                        scope[1], (time.monotonic() - started) * 1000, attempt + 1)
        metric("retries")
        time.sleep(0.25 * (2 ** attempt))
