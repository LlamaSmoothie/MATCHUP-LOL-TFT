# TFTLOL

League of Legends and Teamfight Tactics match-history lookup with a React UI,
a Python API, and a local SQLite TTL cache.

The frontend uses a responsive dark dashboard with teal/coral match results,
grouped champion and item details, and an optional expandable champion table.
It reuses the existing artwork and system fonts, with keyboard focus indicators
and reduced-motion support.

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
This changes the display only; statistics still use the full filtered sample.
**View more history** expands the sample automatically. Queue, role, and patch
filters apply to champion statistics only. Match history and individual AI
reviews are independent of these filters.
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

## Match details and player profiles

Click a match card to open its details, or focus the card and press Enter or Space.
LoL details show both teams' scoreboards, final items, and the searched player's
combat, economy, vision, objective, and team statistics. TFT details show
placements, player statistics, and expandable boards. Missing statistics display
as unavailable. The scoreboard uses the existing raw-match cache. LoL timeline
data loads separately, making one additional Riot request on a cache miss.
Opening details never generates an OpenAI request.

Select a participant's name to search their profile in the same game and region.
The backend resolves their current Riot ID when clicked, including participants
whose older match records lack a full name. A successful lookup is cached for
24 hours and reused by the new profile search. Players without an available
identity have a disabled profile control. Lookup errors leave match details open
so you can retry.

**Back to match history** restores the loaded list, champion filters, scroll
position, and card focus. Searching a participant starts their history at page
one. Restart the Python backend and reload the frontend after updating to enable
the new detail and participant lookup endpoints.

## Completed-match timelines

Opening a LoL match also loads **Match timeline**. Choose gold, experience, CS,
or team gold difference, then move the sample slider to inspect recorded values.
When Riot supplies matching team roles, the chart includes a same-role opponent.
Missing samples stay unavailable; the chart uses actual timestamps and the
returned frame interval rather than assuming every record is exactly one minute.

The event list shows kills, deaths, objectives, and the searched player's item
purchases, sales, removals, undo actions, skill upgrades, and ward events. Filters
and **Show more events** operate on the fetched timeline. Item events are recorded
actions, not build recommendations; repeated purchases are preserved. Riot can
omit or return inconsistent historical events. Timeline snapshots do not provide
a complete replay or continuous movement tracking.

Timelines use `/lol/match/v5/matches/{matchId}/timeline` on the match's regional
host and have a separate 30-day SQLite cache. The server verifies the match and
player mapping before returning normalized data. Missing timelines display an
unavailable state; rate limits and other failures have a retry control. Match
statistics remain usable if the timeline fails. TFT has no equivalent timeline
implemented here; its placement and board details remain available.

## Ongoing games and local live statistics

After a successful profile search, click **Check ongoing game** to check Riot's
Spectator API. No ongoing-game request runs until you click the button.
Only confirmed ongoing games are automatically refreshed, every five seconds
while that profile page is visible. Inactive players receive a single check and
can use **Check again**. Polling stops when the game ends, the player changes,
match details open, the tab is hidden, or a request fails. Returning to the page
requires another manual check. Spectator responses are cached for 15 seconds, so game-start/end
status can briefly lag. A Riot 404 means no *available* active-game record; some
queues or regions may not expose one.

For any available ongoing game, the app shows the queue and participant roster.
For LoL, identified participants also show Solo/Duo and Flex rank, their most-played
champion in the recent sample, average kills/deaths/assists, and the KDA ratio
`(total kills + total assists) / total deaths`. A zero-death sample is labeled
**Deathless sample**. The sample covers up to the latest 20 completed matches across
queues (including ARAM), excluding custom games and incomplete participant records.
This is recent form, not lifetime champion usage or statistics from the ongoing match.
The eligible sample size is displayed; no history and failed lookups are distinct.

Player profiles load progressively, two at a time, only after a manual check finds
an active LoL game. They use Riot's public rank and match APIs and work without the
local game feed. Five-second live refreshes do not reload these profiles. Ranked
entries reuse the five-minute cache, history summaries cache for ten minutes, and raw
matches share the existing cache. A cold ten-player roster can require up to 220
public API calls before cache reuse; rate limits pause queued lookups and display a
retry message. **Retry player stats** retries failed lookups using cached successes.
Leaving the profile or hiding the tab cancels pending browser requests and prevents
queued lookups from starting. Bots and participants without a complete Riot ID are
not looked up. TFT does not have champion/KDA profiles in this view.

For LoL, detailed live KDA, CS, vision, level, items, and recent events additionally
require the matching game client **on the computer running the Python backend**.
The backend reads Riot's fixed `https://127.0.0.1:2999/liveclientdata/allgamedata`
endpoint only after confirming an ongoing game. It checks full Riot IDs, the
named roster, active player, map, and game timing before exposing live statistics.
A disconnected, different, or unverifiable local game does not populate the
live scoreboard. TFT currently shows public ongoing-game information only.

The connection verifies HTTPS using Riot's public root certificate bundled at
`backend/riotgames.pem`; proxies and redirects are disabled for this local read,
and no Riot/OpenAI API key is sent to the game client. Live client statistics are
not saved to SQLite or sent to OpenAI. Set `LOCAL_LIVE_ENABLED=0` on a public
deployment. A hosted server cannot read a visitor's local game client; that would
require a separate desktop companion. Nonlocal browser origins cannot request
local-client data through this endpoint.

If only the roster appears, the message above it explains whether the local
connection was refused, timed out, failed certificate verification, was disabled,
or could not be matched to the searched game. The League launcher alone does not
provide the in-match feed. Finish loading into the match, open the app through
`localhost`, and click **Check ongoing game** again. To diagnose the connection,
run `python scripts/check_live.py` from the backend computer. This performs one
local HTTPS request and prints connection/field availability without player
names, API keys, or a call to Riot's public API. Restart the Python backend after
updating its code or configuration.

## AI match insights

For LoL, open a match and click **Analyze this match** to generate a summary,
observations, optional replay-review questions, and limitations for that game.
AI uses the selected player's end-of-game data: combat, CS, gold, damage, vision,
objectives, sustain, and available team/opponent totals. Successfully loaded
timeline checkpoints and selected combat/objective events provide timing context.
Champion pools, pick
shares, builds, runes, and champion-table filters are not part of AI analysis.
ARAM is included, with queue context to avoid applying Summoner's Rift expectations.

AI runs only on click; searching, loading history, and opening details never wait
for it. The Analyze button waits for the timeline request to settle so a newly
loaded timeline is included; a failed timeline still permits a summary-only review.
AI loading and errors do not block the scoreboard. **Hide insights** /
**Show insights** toggles an existing result without another request. Leaving
details clears the displayed review; clicking Analyze again reuses a valid
server-cached result. **Match statistics** above the AI review shows the key
statistics for the game, with missing values marked unavailable.

Add your OpenAI key to the existing root `config.env` and restart the backend:

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.6-luna
```

The key is read only by Python. Keep real keys out of `config.env.example`, React
code, `VITE_` variables, and Git. For deployment, use the backend host's secret
environment settings. No additional Python dependencies are required.

The browser submits the searched identity and **one match ID** to
`POST /api/analyze`. Python verifies the player belongs to that cached match and
extracts an allowlist of statistics from the raw Riot cache. It never trusts
browser-supplied statistics or fetches extra Riot data for analysis. It reads any
available timeline from the backend cache. If those
cache entries expire, search and load that history again. Restart the backend
and reload the frontend after upgrading from the old champion-summary request.

Per-minute rates use the match duration. CS includes lane and neutral minions;
kill participation is (kills + assists) / team kills; damage and gold shares use
that player's team totals. Missing counters, unknown duration, and zero team
denominators produce unavailable rates. Team objective totals provide context
but do not establish individual participation. Timeline timestamps are retained
in milliseconds, including when samples are reduced for AI input.

Only the selected game's numerical statistics, team totals, queue/map/role/patch
context, and available timeline evidence are sent to OpenAI. Timeline input is
bounded to at most 21 checkpoints and 80 selected combat/objective events;
it excludes inventory, skill, and ward event streams. Riot IDs, PUUIDs, match IDs, champion names,
teammate names, inventories, runes, and credentials are
excluded from model input. The Responses API uses structured JSON output,
`reasoning.effort=none`, `store=false`, and a 1,200-output-token cap. Setting
`store=false` disables stored Responses objects; it is not a promise of zero
provider retention. Model output is rendered as text and can still be inaccurate;
check its observations against the match data. It can describe recorded event
timings and sampled progression when a timeline is available, but cannot
reconstruct a complete replay, diagnose positioning or lane mistakes, or establish
causes of a win or loss. It does not supply global benchmarks or live coaching.

Successful analyses are cached for 24 hours in SQLite, isolated by player,
routing region, match ID, extracted evidence, model, and prompt version. The new
prompt version and evidence fingerprint prevent reuse of older summary-only
results when timeline evidence becomes available. Concurrent
identical requests share one generation.
Errors, refusals, incomplete responses, and invalid JSON are not cached. New
provider attempts default to one at a time, at least 10 seconds apart, and at most
100 per UTC day across this backend. Daily counts persist in SQLite; failures
count as attempts and cache hits do not. OpenAI 429 responses establish a shared
cooldown. Requests are not automatically retried, avoiding duplicate paid calls.
Run one backend process for these shared concurrency controls. These application
limits do not replace access controls for a public deployment or limits on other
applications using the same OpenAI project.

An optional **paid** live check sends one fictional match to OpenAI
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
GET /api/match?game=lol&region=North%20America&name=GameName%23TagLine&matchId=NA1_1234567890
GET /api/match-player?game=lol&region=North%20America&name=GameName%23TagLine&matchId=NA1_1234567890&participant=0
GET /api/match-timeline?game=lol&region=North%20America&name=GameName%23TagLine&matchId=NA1_1234567890
GET /api/live-game?game=lol&region=North%20America&name=GameName%23TagLine
GET /api/live-player?game=lol&region=North%20America&name=GameName%23TagLine&gameId=1234567890&participant=0
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

Match details require a match ID from the loaded search. The response contains
`game`, `matchId`, `match` (the searched player's statistics/context), `playerName`,
and `participants` (scoreboard rows with `index`, `name`, and `canSearch`).
Participant lookup takes a row's `index` as `participant` and returns
`{game, region, name}` for a new search. Both endpoints verify the source player
belongs to the cached match; expired source-account or match entries return 409.
Participant lookup resolves the selected PUUID through Riot Account-V1 only on
click; it does not resolve every scoreboard name up front or generate AI output.

Timeline responses contain `available`, `samples`, `events`, player mappings, and
the recorded `frameInterval`. A missing upstream timeline returns `available: false`;
authentication, rate-limit, and invalid-data failures remain errors.
Ongoing-game responses contain `active`, `pollAfter`, and, when active, the public
participant roster plus a `local` status. Only `local.status = connected` includes
local live statistics. The browser cannot supply a local host or URL to query.
`/api/live-player` resolves a participant index against the searched player's
fresh cached ongoing-game roster. It returns separate `rank` and `history` states
without exposing PUUIDs. It rejects expired or changed games and arbitrary player
indices before requesting historical data. If the Spectator cache is explicitly
disabled with a zero TTL, each participant request reconfirms the ongoing game.

Analysis accepts `Content-Type: application/json` with a maximum 32 KiB body:

```json
{
  "game": "lol",
  "region": "North America",
  "name": "GameName#TagLine",
  "matchId": "NA1_1234567890"
}
```

Use a real ID from the loaded search results. Champion filters and client-side
statistics are not accepted. The response contains
`analysis` (`summary`, `observations`, `reviewSuggestions`, `limitations`),
`matchId`, `match` (the evidence used), `model`, and `generatedAt` (Unix seconds).
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
| Participant PUUID to Riot ID | Game, routing region, PUUID | 24 hours |
| Match-ID page | Game, routing region, PUUID, offset, count, time boundary | 60 seconds |
| Raw match details | Game, routing region, match ID | 30 days |
| Completed LoL timeline | Game, routing region, match ID | 30 days |
| Active game / no available game | Game, platform, PUUID | 15 seconds |
| Ongoing roster history summary | Version, game, platform, routing, PUUID, sample size | 10 minutes |
| Ongoing roster match IDs | Game, routing, PUUID, sample size | 60 seconds |

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
| `TIMELINE_TTL_SECONDS` | `2592000` | Completed LoL timeline TTL |
| `ACTIVE_GAME_TTL_SECONDS` | `15` | Spectator status TTL, 0–60 seconds |
| `LIVE_PROFILE_TTL_SECONDS` | `600` | Ongoing roster historical summary TTL, 0–3600 seconds |
| `LOCAL_LIVE_ENABLED` | `1` | Set to `0` to disable reads from the local game client |
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
[match timelines](https://developer.riotgames.com/apis#match-v5/GET_getTimeline),
[local game client API and certificate](https://developer.riotgames.com/docs/lol#game-client-api),
[Vite assets](https://vite.dev/guide/assets).
