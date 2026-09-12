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

## Player champion statistics

After a LoL search, **Champion statistics** summarizes the searched player's
loaded matches by champion: games, wins/losses, win rate, personal pick share,
average kills/deaths/assists, and overall KDA. Only the most-played champion is
shown initially; **Show more champions** expands the remaining rows, and **Show
less** collapses them. Changing or clearing filters returns to one champion.
This changes the display only; statistics and AI still use the full filtered
sample. **View more history** expands the
sample automatically. Queue, role, and patch filters apply only to this table.
Searching another player or switching games clears the previous statistics.

Rates describe the loaded sample, not lifetime performance or global champion
statistics. Eligible matches have a champion ID and a Victory/Defeat result;
remakes are included if Riot records them that way. Win rate is wins divided by
champion games; personal pick share is champion games divided by all eligible
matches matching the filters. KDA is total kills plus assists divided by total
deaths, with a separate deathless label. Missing combat data is excluded from
KDA averages and its coverage is shown.

Open **Items & runes** on a champion to see the six most frequent final-inventory
items and three most frequent primary/secondary rune combinations, with usage
counts and data coverage. Items count once per game and exclude the trinket slot.
These are observed inventories, not purchase sequences or recommended builds.
Rune combinations exclude stat shards. Missing historical data stays unavailable
instead of being counted as zero.

The backend supplies these fields from the already fetched/cached Match-V5
participant for the searched PUUID. The frontend computes statistics from unique
loaded match IDs; filtering and expanding details make no additional Riot API
calls. Restart an already-running Python backend to expose the new fields; the
existing raw-match cache can be reused without clearing it.

## AI match insights

For LoL, click **Analyze my matches** below the champion table to generate a
summary, observations, optional replay-review questions, and limitations using
the current queue/role/patch filters. AI runs only on click; searching and loading
the screen never wait for it. Loading another page, changing filters, or searching
another player clears the analysis. Failed AI requests leave match history intact.

Add your OpenAI key to the existing root `config.env` and restart the backend:

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.6-luna
```

The key is read only by Python. Keep real keys out of `config.env.example`, React
code, `VITE_` variables, and Git. For deployment, use the backend host's secret
environment settings. No additional Python dependencies are required.

The browser submits the searched identity, loaded match IDs, and filters to
`POST /api/analyze`. Python verifies the player belongs to each cached match and
recomputes statistics from the raw Riot cache; it never trusts browser-supplied
statistics or fetches extra Riot matches for analysis. If those cache entries
expire, search and load that history again. A request accepts up to **200 loaded
matches** and includes details for the **10 most-played champions** matching the
filters. Rates still use all eligible filtered matches as their denominator.

Only aggregate statistics, champion/item/rune names, and filter/patch context are
sent to OpenAI. Riot IDs, PUUIDs, match IDs, teammate names, and credentials are
excluded from model input. The Responses API uses structured JSON output,
`reasoning.effort=none`, `store=false`, and a 1,200-output-token cap. Setting
`store=false` disables stored Responses objects; it is not a promise of zero
provider retention. Model output is rendered as text and can still be inaccurate;
check its observations against the table. It cannot diagnose mistakes from KDA
alone, establish build effectiveness, or supply global benchmarks.

Successful analyses are cached for 24 hours in SQLite, isolated by player,
routing region, match sample, filters, calculated statistics, metadata version,
model, and prompt version. Concurrent identical requests share one generation.
Errors, refusals, incomplete responses, and invalid JSON are not cached. New
provider attempts default to one at a time, at least 10 seconds apart, and at most
100 per UTC day across this backend. Daily counts persist in SQLite; failures
count as attempts and cache hits do not. OpenAI 429 responses establish a shared
cooldown. Requests are not automatically retried, avoiding duplicate paid calls.
Run one backend process for these shared concurrency controls. These application
limits do not replace access controls for a public deployment or limits on other
applications using the same OpenAI project.

An optional **paid** live check sends one fictional two-match sample to OpenAI
without reading player history or using Riot:

```powershell
npm run check:ai
```

It validates the response structure and never prints the key. Offline tests and
CI mock OpenAI and make no paid requests. The live check bypasses the app's
analysis cache and daily counter, so each invocation makes a new provider request.
See [Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Loading performance

The initial screen renders without waiting for the backend or Riot. Game images
load directly from Riot's Data Dragon CDN, using a small filename map bundled
with the app. Match images load lazily as they approach the viewport. Branding,
the fallback image, and LoL rank badges are served locally from `assets/`.

After resolving a Riot ID, the backend requests profile, rank, and match IDs
concurrently. Match downloads can begin while profile/rank requests are still
pending. All upstream calls share `RIOT_MAX_CONCURRENCY`; repeated searches reuse
the TTL cache. An uncached search still needs live Riot requests, so its duration
depends on Riot's response times and any retries or rate limits.

## Game images and storage

Profile icons, LoL champions, items, summoner spells, TFT units, and TFT rank
images use versioned HTTPS URLs on `ddragon.leagueoflegends.com`. These public
image requests need no Riot API key. Numeric LoL champion IDs are mapped to image
filenames; TFT uses its separate character-ID mapping. Missing, older-set, or
unavailable CDN images fall back to the local TFT logo without retry loops.

`frontend/src/riot-assets.json` pins the CDN version, filename mappings, champion
and item names, and rune names/icon paths. Rune icons use Riot's unversioned
`/cdn/img/perk-images/` URLs. Historical IDs absent from the pinned metadata
display an ID label and use the existing image fallback. The metadata is
checked into Git, so normal builds and browser startup make **no metadata
requests**. The initial pinned version is `16.18.1`. To update intentionally:

```powershell
npm run assets:update
# Or pin a specific patch:
npm run assets:update -- --version 16.18.1
npm run check:cdn
npm test
npm run build
npm run check:build
```

The updater caches metadata downloads for 24 hours under ignored
`data/cache/ddragon/`; `--force` bypasses that cache. It replaces the bundled map
only after every metadata category loads and validates successfully. Review and
commit the changed map after checking its images. Riot's metadata can lag a patch,
and the pinned map only covers the sets Riot includes in that version.

Only 11 images (about 1 MiB) remain in the active `assets/` folder. The 4,111
retired images were moved into `archive/assets/` and hash-verified, preserving
the earlier no-deletion requirement. The archive is excluded from the build but
still occupies disk space. Images are also recoverable from the Git checkpoint
`recovery/local-assets-2026-09-11`.

The verified production output dropped from about **412 MiB to 1.25 MiB** with
this migration. The 3 MiB build check guards against copying the large catalog
back into deployment output accidentally.

CDN delivery reduces deployment storage and image traffic through your server;
loading game artwork depends on internet access. See [Git recovery instructions](docs/RECOVERY.md)
to return to the complete local-image application.

## API

```text
GET /api/health
GET /api/riot-status?game=tft&region=North%20America
GET /api/recent-searches?limit=10
GET /api/search?game=lol&region=North%20America&name=GameName%23TagLine&start=0&count=10
POST /api/analyze
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

Analysis accepts `Content-Type: application/json` with a maximum 32 KiB body:

```json
{
  "game": "lol",
  "region": "North America",
  "name": "GameName#TagLine",
  "matchIds": ["NA1_1234567890"],
  "filters": {"queue": "", "role": "", "patch": ""}
}
```

Use real IDs from loaded search results. Empty filter strings mean all; queue
uses its numeric ID as a string, role uses `TOP`, `JUNGLE`, `MIDDLE`, `BOTTOM`,
`UTILITY`, or `UNKNOWN`, and patch uses e.g. `16.18`. The response contains
`analysis` (`summary`, `observations`, `reviewSuggestions`, `limitations`),
`sample` coverage/filter metadata, `model`, and `generatedAt` (Unix seconds).
Missing cache entries return 409, usage limits return 429 with `Retry-After`,
and missing/rejected OpenAI configuration returns 503. Cross-site browser POSTs
are rejected; the current frontend and API use the same origin through Vite.

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
| `OPENAI_API_KEY` | Unset | Optional backend key enabling AI insights |
| `OPENAI_MODEL` | `gpt-5.6-luna` | Responses model supporting structured output and reasoning `none` |
| `OPENAI_TIMEOUT_SECONDS` | `30` | OpenAI request timeout, 1–60 seconds |
| `AI_CACHE_TTL_SECONDS` | `86400` | Successful analysis cache TTL; zero disables reuse |
| `AI_MIN_INTERVAL_SECONDS` | `10` | Minimum interval between new provider attempts, 0–3600 seconds |
| `AI_DAILY_REQUEST_LIMIT` | `100` | Server-wide provider attempts per UTC day; zero blocks new generations |

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
Python service. Only local branding/fallback art and LoL rank badges are included
in the build; the other game images are loaded from Riot's CDN. The current
filename map and local fallback are included even for offline builds.

Optional live tests, using the key in `config.env`:

```powershell
npm run check:riot -- --game lol
npm run check:riot -- --game tft
npm run check:riot -- --game lol --riot-id "GameName#TagLine"
```

The legacy `--summoner` flag is accepted as an alias for `--riot-id`.
GitHub Actions runs offline Python tests, frontend tests, and the Vite build on
Windows and Linux. Champion-statistics tests cover player isolation, formulas,
filters, duplicate matches, missing fields, item/rune grouping, and pagination.
`check:frontend` verifies that startup has no image-module
imports, local artwork is served, and game images resolve to CDN URLs.
`check:build` verifies local files, excludes retired image folders, and limits the
build to 3 MiB. `check:cdn` is an optional live image check with no API key.

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
│   │   └── riot-assets.json  Pinned Riot CDN version and compact filename map
│   ├── vite.config.js        Frontend root, shared assets, API proxy
│   └── dist/                 Generated production build (ignored by Git)
├── assets/                   Local branding/fallback images and LoL rank badges
├── data/
│   ├── static/               Active queues.json and summoner.json reference data
│   ├── cache/ddragon/        Optional metadata download cache (ignored by Git)
│   └── tftlol.sqlite3         Existing runtime database (ignored by Git)
├── scripts/                  Frontend/build checks and optional live Riot checks
├── tests/
│   ├── backend/              Python offline regression tests
│   └── frontend/             JavaScript request-state and image tests
├── archive/                  Historical code, data, artwork, and previous output
│   └── assets/               Retired local game images, excluded from builds
├── docs/RECOVERY.md           Git checkpoint and rollback instructions
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
