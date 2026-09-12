"""Local JSON API. Match lookup and caching live in match_service."""
import json
import logging
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import app_database
from .analysis_service import analyze
from .match_service import search, test_riot_connection
from .riot_client import ApiError, metrics_snapshot

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
LOGGER = logging.getLogger(__name__)


def parameter(query, name, default=None):
    values = query.get(name, [default])
    if len(values) != 1:
        raise ApiError(f"{name} must be supplied only once.")
    return values[0]


def integer_parameter(query, name, default=None):
    value = parameter(query, name, default)
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ApiError(f"{name} must be an integer.") from None


class ApiHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if self.path != "/api/analyze":
                raise ApiError("Not found", 404)
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise ApiError("Analysis must be requested from this application.", 403)
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise ApiError("Analysis requires application/json.", 415)
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not lengths[0].isdigit():
                raise ApiError("Provide a valid Content-Length.")
            length = int(lengths[0])
            if not 1 <= length <= 32768:
                raise ApiError("Analysis request exceeds the 32 KiB limit.", 413)
            self.connection.settimeout(10)
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete body")
                payload = json.loads(raw)
            except (ValueError, UnicodeError):
                raise ApiError("Provide a valid JSON analysis request.") from None
            self.write_json(analyze(payload))
        except ApiError as error:
            self.write_json({"error": str(error),
                             **({"retryAfter": error.retry_after} if error.retry_after else {})},
                            error.status, error.retry_after)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception as error:
            # Do not log request bodies, player data, credentials, or provider errors.
            LOGGER.error("analysis_error type=%s", type(error).__name__)
            self.write_json({"error": "The backend could not complete the analysis."}, 500)

    def do_GET(self):
        started = time.monotonic()
        parsed = urlparse(self.path)
        try:
            query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=20)
        except ValueError:
            self.write_json({"error": "Too many query parameters."}, 400)
            return
        try:
            if parsed.path == "/api/health":
                result = {"ok": True}
            elif parsed.path == "/api/recent-searches":
                limit = integer_parameter(query, "limit", "10")
                if not 1 <= limit <= 50:
                    raise ApiError("limit must be between 1 and 50.")
                result = {"searches": app_database.recent_searches(limit)}
            elif parsed.path == "/api/riot-status":
                result = test_riot_connection(
                    parameter(query, "game", "lol"),
                    parameter(query, "region", "North America"),
                )
            elif parsed.path == "/api/search":
                refresh = parameter(query, "refresh", "0")
                if refresh not in {"0", "1"}:
                    raise ApiError("refresh must be 0 or 1.")
                result = search(
                    game=parameter(query, "game", "lol"),
                    region=parameter(query, "region", "North America"),
                    name=parameter(query, "name", ""),
                    start=integer_parameter(query, "start", "0"),
                    count=integer_parameter(query, "count", "10"),
                    as_of=integer_parameter(query, "asOf"),
                    refresh=refresh == "1",
                )
            else:
                raise ApiError("Not found", 404)
            self.write_json(result)
        except ApiError as error:
            self.write_json({"ok": False, "error": str(error),
                             **({"retryAfter": error.retry_after} if error.retry_after else {})},
                            error.status, error.retry_after)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            LOGGER.exception("backend_error path=%s", parsed.path)
            self.write_json({"error": "The backend could not complete this request."}, 500)
        finally:
            LOGGER.info("api_request path=%s duration_ms=%.0f counters=%s",
                        parsed.path, (time.monotonic() - started) * 1000, metrics_snapshot())

    def write_json(self, data, status=200, retry_after=None):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        # Default HTTP logs include the complete Riot ID query string.
        pass


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app_database.init_db()
    app_database.cleanup_expired(force=True)
    port = int(os.getenv("API_PORT", DEFAULT_PORT))
    with ThreadingHTTPServer((DEFAULT_HOST, port), ApiHandler) as server:
        LOGGER.info("API server listening on http://%s:%s", DEFAULT_HOST, port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
