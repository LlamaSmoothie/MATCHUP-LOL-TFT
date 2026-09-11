# TFTLOL

League of Legends and Teamfight Tactics match-history lookup with a React UI,
a Python API, and a local SQLite TTL cache.

## Run locally

Use Python 3.10+ and Node.js 22+. The web backend uses only Python's standard
library. Legacy Qt dependencies are preserved in
`archive/desktop/requirements.txt` and are not needed for the web app.

```powershell
npm install
if (-not (Test-Path config.env)) { Copy-Item config.env.example config.env }
# Edit config.env and set RIOT_API_KEY.
npm run backend
```

In a second terminal:

```powershell
npm run dev
```

Open the URL printed by Vite. Enter a complete **Riot ID**, such as
`GameName#TagLine`, and select the player's region. Bare summoner names are no
longer supported. If PowerShell blocks `npm.ps1`, use `npm.cmd` for the same commands.

Vite proxies `/api` to `http://127.0.0.1:8000`. The API binds to localhost.
The **Test Riot API** button checks the selected game's platform-status endpoint.
API keys stay in the Python process and are sent to Riot using `X-Riot-Token`.

## Pagination and refresh

Search loads 10 matches. **View more history** appends the next page and disappears
when there are no more matches. Editing the form does not change the submitted
search used by Load more or Refresh; submit the form to search another player.

The first page returns an `asOf` Unix timestamp in seconds. Later requests must
send it back. Both games use Riot's `endTime` filter so newer matches do not shift
the page offsets. The server requests one extra match ID to detect another page,
but only downloads details for the displayed matches.

Refresh starts again at page zero with a fresh profile, rank, and match list.
It reuses valid account and historical match-detail cache entries. Failed later
pages keep the loaded matches and the same next offset for retry. The UI cancels
obsolete requests, ignores late responses, and deduplicates matches by ID.

Win rate is calculated over all loaded LoL matches; TFT shows top-four rate.
Relative ages are calculated from match timestamps and update every minute.

## Loading performance

The initial screen renders without waiting for the backend or Riot. Images are
served directly from `assets/`; the browser no longer imports the entire image
catalog as JavaScript before starting React. Match images load lazily as they
approach the viewport, with a fallback for missing artwork.

After resolving a Riot ID, the backend requests profile, rank, and match IDs
concurrently. Match downloads can begin while profile/rank requests are still
pending. All upstream calls share `RIOT_MAX_CONCURRENCY`; repeated searches reuse
the TTL cache. An uncached search still needs live Riot requests, so its duration
depends on Riot's response times and any retries or rate limits.

## API

```text
GET /api/health
GET /api/riot-status?game=tft&region=North%20America
GET /api/recent-searches?limit=10
GET /api/search?game=lol&region=North%20America&name=GameName%23TagLine&start=0&count=10
```

Search responses contain `profile`, `matches`, and:

```json
{
  "pagination": {
    "start": 0,
    "count": 10,
    "asOf": 1789100000,
    "nextStart": 10,
    "hasMore": true
  },
  "nextStart": 10
}
```

For the next page, send `start=10&count=10&asOf=<returned timestamp>`.
At the end, `hasMore` is false and `nextStart` is null. The top-level
`nextStart` is retained for compatibility. `count` accepts 1–20;
`start` accepts non-negative integers. Invalid inputs return JSON with HTTP 400.

Use `refresh=1` only on a new first-page request, without `asOf`.
The endpoint deliberately returns no total-match count because Riot does not
provide one. The time boundary is not an atomic upstream snapshot: late-indexed
Riot matches may still change old history.

## SQLite and TTL caching

The default database is `data/tftlol.sqlite3`. Cached values have a schema version,
fetch time, and expiry time. Reads do not extend expiry. Successful empty lists
are cached; network errors, rate limits, and authentication failures are not.

| Data | Cache key | Default TTL |
| --- | --- | --- |
| Riot ID → account | Game, routing region, complete normalized Riot ID | 24 hours |
| Profile and ranked entries | Game, platform, PUUID | 5 minutes |
| Match-ID page | Game, routing region, PUUID, offset, count, time boundary | 60 seconds |
| Raw match details | Game, routing region, match ID | 30 days |

First pages reuse their cached time boundary during the match-list TTL.
Raw match details are shared between player searches and normalized for each
player after retrieval. All pages are cached. Repeating a fully cached search
before expiry makes zero Riot requests.

Recent-search history is keyed by game, platform, and PUUID. Its timestamp
records user searches, independently of cache freshness. The complete Riot ID,
including tagline, is retained. Existing legacy database tables are preserved,
but their ambiguous name-based records are not used for new searches.

Expired entries are removed at startup and periodically during cache writes.
SQLite connections close after each operation. Concurrent misses for the same
key share one fetch within a backend process. Run one backend process for shared
cooldown and request coordination; SQLite persists the cache across restarts.

## Configuration

Environment variables override values in `config.env`. Do not commit that file.

| Variable | Default | Purpose |
| --- | --- | --- |
| `RIOT_API_KEY` | Required | Shared fallback key |
| `LOL_API_KEY`, `TFT_API_KEY` | Unset | Optional game-specific keys |
| `DATABASE_PATH` | `data/tftlol.sqlite3` | SQLite file |
| `API_PORT` | `8000` | Backend port; also update Vite's proxy if changed |
| `ACCOUNT_TTL_SECONDS` | `86400` | Account lookup TTL |
| `PROFILE_TTL_SECONDS` | `300` | Profile/rank TTL |
| `MATCH_LIST_TTL_SECONDS` | `60` | Match-ID page TTL |
| `MATCH_TTL_SECONDS` | `2592000` | Raw match TTL |
| `CACHE_CLEANUP_INTERVAL_SECONDS` | `3600` | Minimum cleanup interval |
| `RIOT_MAX_CONCURRENCY` | `3` | Shared request limit, 1–8 |
| `RIOT_TIMEOUT_SECONDS` | `15` | Per-attempt timeout, 1–30 seconds |
| `RIOT_MAX_RETRIES` | `2` | Retries after transient failures, 0–3 |

A TTL of zero disables reuse for that layer. Transient network/5xx errors use
bounded exponential backoff. A 429 establishes a shared cooldown for the key and
host; the API returns `Retry-After` and `retryAfter` to the UI instead of holding
an HTTP request open throughout the cooldown. Logs include request durations and
cumulative cache/upstream counters without logging credentials or Riot ID URLs.

## Tests and production build

Offline tests use temporary databases and mocked Riot responses:

```powershell
npm run test:backend
npm test
npm run check:frontend
npm run build
npm run check:build
npm run preview
```

Preview serves the built UI and proxies API requests to the running backend.
For deployment, serve `frontend/dist/` through your web server and proxy `/api` to the
Python service. All locally available game images are included in the build.
Missing/newer assets use a fallback image; the bundled game data is an older
snapshot and does not contain current TFT-set artwork.

Optional live tests, using the key in `config.env`:

```powershell
npm run check:riot -- --game lol
npm run check:riot -- --game tft
npm run check:riot -- --game lol --riot-id "GameName#TagLine"
```

The legacy `--summoner` flag is accepted as an alias for `--riot-id`.
GitHub Actions runs offline Python tests, frontend tests, and the Vite build on
Windows and Linux. `check:frontend` verifies that startup has no image-module
imports and that Vite serves every image category. `check:build` verifies the
bundled URLs and that the entire public image catalog was copied into the build.

## Project layout

Run all npm commands from the repository root. One root `package.json` and lockfile
manage the frontend tooling and the Python launch/check commands.

```text
TFTLOL.git/
├── backend/                  Python package: API, Riot client, cache, match service
│   ├── __main__.py           Entry point for python -m backend
│   ├── api_server.py         HTTP routes and JSON errors
│   ├── app_config.py         Loads root config.env; defines Riot routing
│   ├── app_database.py       SQLite persistence
│   ├── match_service.py      Pagination, caching, normalization
│   └── riot_client.py        Transport, retries, rate-limit cooldown
├── frontend/
│   ├── index.html            Browser entry point
│   ├── src/                  React components, request state, styles, image helpers
│   ├── vite.config.js        Frontend root, shared assets, API proxy
│   └── dist/                 Generated production build (ignored by Git)
├── assets/                   Shared champion, item, profile, rank, spell, and UI images
├── data/
│   ├── static/               Active queues.json and summoner.json reference data
│   └── tftlol.sqlite3         Existing runtime database (ignored by Git)
├── scripts/                  Frontend/build checks and optional live Riot checks
├── tests/
│   ├── backend/              Python offline regression tests
│   └── frontend/             JavaScript request-state and image tests
├── archive/                  Historical code, data, artwork, and previous output
├── .github/workflows/        Application checks on Windows and Linux
├── config.env                Local secrets/settings; kept in place and ignored
├── config.env.example        Configuration template
├── package.json              Root commands and frontend dependencies
└── package-lock.json         Dependency lockfile
```

`node_modules/` remains at the root as generated dependency storage. Existing
IDE and agent metadata remain in their original hidden directories.

The web app does not import archived code. The archived `SearchMatch` adapter
still uses the active backend and is covered by the compatibility regression test.
The historical Qt screens, prototype, downloader, old data, and unused artwork
are documented in [archive/README.md](archive/README.md).

No existing files were deleted during reorganization. Previous build output,
bytecode caches, and logs were moved into the archive. Each move was checked by
SHA-256 before path/import updates; the chronological record is in
[archive/move-manifest.json](archive/move-manifest.json). `config.env` and the
existing SQLite database stayed in place.

Endpoint and implementation references:
[Riot API reference](https://developer.riotgames.com/apis),
[Riot ID migration](https://www.riotgames.com/en/DevRel/summoner-names-to-riot-id),
[regional routing and merged SEA platforms](https://support-developer.riotgames.com/hc/en-us/articles/22698698001939-League-of-Legends),
[rate limits](https://developer.riotgames.com/docs/portal#web-apis_rate-limiting),
[Vite assets](https://vite.dev/guide/assets).
