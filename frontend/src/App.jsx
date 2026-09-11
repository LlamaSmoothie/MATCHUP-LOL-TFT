import React from 'react';
import { Search, RefreshCw, Trophy, Shield, Swords, Clock3 } from 'lucide-react';
import { asset } from './assets.js';
import GameImage from './GameImage.jsx';
import { createMatchHistory, formatAge, matchSummary } from './matchHistory.js';

const regions = [
  'North America',
  'Brazil',
  'EU Nordic & East',
  'EU West',
  'Japan',
  'Korea',
  'Latin America North',
  'Latin America South',
  'Oceania',
  'Philippines',
  'Russia',
  'Singapore',
  'Thailand',
  'Turkey',
  'Taiwan',
  'Vietnam',
];


function App() {
  const [game, setGame] = React.useState('lol');
  const [query, setQuery] = React.useState('');
  const [region, setRegion] = React.useState(regions[0]);
  const [history] = React.useState(() => createMatchHistory());
  const { data, error, loading, identity } = React.useSyncExternalStore(
    history.subscribe, history.getSnapshot,
  );
  const [connection, setConnection] = React.useState(null);
  const [testingConnection, setTestingConnection] = React.useState(false);
  const connectionRequest = React.useRef(null);
  const [now, setNow] = React.useState(Date.now);

  React.useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000);
    return () => { clearInterval(timer); history.cancel(); connectionRequest.current?.abort(); };
  }, [history]);

  function submitSearch(event) {
    event.preventDefault();
    history.search({ game, region, name: query });
  }

  async function testRiotConnection() {
    connectionRequest.current?.abort();
    const request = new AbortController();
    connectionRequest.current = request;
    setTestingConnection(true);
    setConnection(null);
    try {
      const params = new URLSearchParams({ game, region });
      const response = await fetch(`/api/riot-status?${params}`, { signal: request.signal });
      const payload = await response.json();
      if (connectionRequest.current !== request) return;
      if (!response.ok) throw new Error(payload.error || 'Riot API connection failed.');
      setConnection({ ok: true, message: `Riot API reachable: ${payload.riotService} (${payload.platform})` });
    } catch (error) {
      if (connectionRequest.current === request && error.name !== 'AbortError') {
        setConnection({ ok: false, message: error.message });
      }
    } finally {
      if (connectionRequest.current === request) setTestingConnection(false);
    }
  }

  function changeGame(nextGame) {
    history.reset();
    connectionRequest.current?.abort();
    connectionRequest.current = null;
    setTestingConnection(false);
    setGame(nextGame);
    setConnection(null);
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <GameImage loading="eager" className="brand-mark" src={asset('picture/TFT.png')} alt="" />
        <button className={game === 'lol' ? 'nav-item active' : 'nav-item'} onClick={() => changeGame('lol')}>
          <Swords size={20} />
          LOL
        </button>
        <button className={game === 'tft' ? 'nav-item active' : 'nav-item'} onClick={() => changeGame('tft')}>
          <Shield size={20} />
          TFT
        </button>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Match Up History</p>
            <h1>{game === 'lol' ? 'League of Legends' : 'Teamfight Tactics'}</h1>
          </div>
          <button className="icon-button" title="Refresh results" onClick={() => history.refresh()} disabled={loading || !identity}>
            <RefreshCw size={18} />
          </button>
        </header>

        <form className="search-panel" onSubmit={submitSearch}>
          <label>
            Riot ID
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="GameName#TagLine"
              required
            />
          </label>
          <label>
            Region
            <select value={region} onChange={(event) => setRegion(event.target.value)}>
              {regions.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
          <button className="primary-button" type="submit" disabled={loading}>
            <Search size={18} />
            {loading ? 'Searching' : 'Search'}
          </button>
          <button className="secondary-button inline-button" type="button" disabled={testingConnection} onClick={testRiotConnection}>
            {testingConnection ? 'Testing' : 'Test Riot API'}
          </button>
        </form>

        {connection ? (
          <div className={connection.ok ? 'status-panel ok' : 'status-panel fail'}>{connection.message}</div>
        ) : null}
        {error ? <div className="error-panel" role="alert">{error}</div> : null}

        {data ? (
          <>
            <ProfileSummary game={game} profile={data.profile} matches={data.matches} />
            <section className="history-list" aria-label="Match history" aria-busy={loading}>
              {data.matches.length > 0 ? data.matches.map((match) =>
                game === 'lol' ? <LolMatchCard key={match.id} match={match} now={now} /> : <TftMatchCard key={match.id} match={match} now={now} />,
              ) : <div className="empty-row">No match history returned.</div>}
              {data.pagination.hasMore ? (
                <button className="secondary-button" disabled={loading} onClick={() => history.loadMore()}>
                  {loading ? 'Loading' : 'View more history'}
                </button>
              ) : data.matches.length > 0 ? <p role="status">All available history loaded.</p> : null}
            </section>
          </>
        ) : (
          <EmptyState game={game} loading={loading} />
        )}
      </section>
    </main>
  );
}

function ProfileSummary({ game, profile, matches }) {
  const summary = matchSummary(game, matches);
  const isLol = game === 'lol';
  const rank = profile.rank || 'N/A';
  const rankAsset = isLol
    ? `ranked-emblem/emblem-${rank.toLowerCase()}.png`
    : `tft-regalia/${rank === 'N/A' ? 'PROVISIONAL' : rank}`;

  return (
    <section className="profile-summary">
      <div className="profile-person">
        <GameImage src={asset(`profileicon/${profile.profileIconId}.png`)} alt="" />
        <div>
          <h2>{profile.name}</h2>
          <p>Level {profile.level} - {profile.region}</p>
        </div>
      </div>
      <div className="rank-block">
        <GameImage src={asset(rankAsset)} alt="" />
        <div>
          <p className="label">Rank</p>
          <strong>{rank}</strong>
        </div>
      </div>
      <div className="win-rate">
        <div className="donut" aria-hidden="true" style={{
          background: summary.percent === null ? '#d6e3eb'
            : `conic-gradient(#21bdd7 0 ${summary.percent}%, #e55353 ${summary.percent}% 100%)`,
        }} />
        <div>
          <p className="label">{summary.label}</p>
          <strong>{summary.percent === null ? 'N/A' : `${summary.percent}%`}</strong>
          <p>Across {summary.count} loaded matches</p>
        </div>
      </div>
    </section>
  );
}

function LolMatchCard({ match, now }) {
  const won = match.result === 'Victory';

  return (
    <article className={won ? 'match-card win' : 'match-card loss'}>
      <div className="match-meta">
        <strong>{match.queue}</strong>
        <span>
          <Clock3 size={14} />
          {formatAge(match.timestamp, now)}
        </span>
        <b>{match.result}</b>
        <span>{match.duration}</span>
      </div>
      <div className="champion-block">
        <GameImage className="champion-icon" src={asset(`champion-icon/${match.champion}.png`)} alt="" />
        <div className="spell-stack">
          {match.spells.filter(Boolean).map((spell, index) => (
            <GameImage key={`${spell}-${index}`} src={asset(`summonerSpell/${spell}`)} alt="" />
          ))}
        </div>
        <div>
          <p>Lv. {match.level}</p>
          <h3>{match.kda}</h3>
          <span>{match.ratio}</span>
        </div>
      </div>
      <div className="item-row">
        {match.items.map((item, index) => (
          <GameImage key={`${item}-${index}`} src={asset(`item/${item}.png`)} alt="" />
        ))}
      </div>
      <ParticipantList match={match} />
    </article>
  );
}

function ParticipantList({ match }) {
  return (
    <div className="participant-grid">
      {[match.teamA, match.teamB].map((team, index) => (
        <div key={index}>
          {team.map((participant) => (
            <span className="participant" key={`${participant.champion}-${participant.name}`}>
              <GameImage src={asset(`champion-icon/${participant.champion}.png`)} alt="" />
              {participant.name}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

function TftMatchCard({ match, now }) {
  return (
    <article className="match-card tft-card">
      <div className="match-meta">
        <strong>{match.placement}</strong>
        <span>{match.queue}</span>
        <span>
          <Clock3 size={14} />
          {formatAge(match.timestamp, now)}
        </span>
      </div>
      <div className="unit-board">
        {match.units.map((unit, index) => (
          <div className="unit" key={`${match.id}-${index}`}>
            <GameImage src={asset(`tft-champion/${unit.champion}`)} alt="" />
            <span>{unit.name}</span>
          </div>
        ))}
      </div>
      <div className="trait-row">
        {match.traits.map((trait) => (
          <span key={trait}>
            <Trophy size={14} />
            {trait}
          </span>
        ))}
      </div>
    </article>
  );
}

function EmptyState({ game, loading }) {
  return (
    <section className="empty-state">
      <GameImage loading="eager" src={asset(game === 'lol' ? 'picture/yasuo.png' : 'picture/TFT.png')} alt="" />
      <div>
        <h2>{loading ? 'Searching match history' : game === 'lol' ? 'Search a Riot ID to see LOL history' : 'Search a Riot ID to see TFT history'}</h2>
        <p>{loading ? 'Finding recent matches.' : 'Enter a Riot ID and select the player’s region.'}</p>
      </div>
    </section>
  );
}

export default App;
