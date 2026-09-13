import React from 'react';
import {
  Search, RefreshCw, Trophy, Shield, Swords, Clock3, ArrowRight,
  ChevronDown, ChartNoAxesCombined, Sparkles, Globe2, LoaderCircle,
} from 'lucide-react';
import { asset, championName, itemName } from './assets.js';
import GameImage from './GameImage.jsx';
import ChampionStats from './ChampionStats.jsx';
import MatchDetail from './MatchDetail.jsx';
import LiveGame from './LiveGame.jsx';
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
    history.subscribe, history.getSnapshot, history.getSnapshot,
  );
  const [now, setNow] = React.useState(Date.now);
  const [selectedMatch, setSelectedMatch] = React.useState(null);
  const returnTo = React.useRef(null);

  React.useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000);
    return () => { clearInterval(timer); history.cancel(); };
  }, [history]);

  React.useEffect(() => {
    if (!selectedMatch && returnTo.current) {
      returnTo.current.button?.focus({ preventScroll: true });
      window.scrollTo({ top: returnTo.current.scrollY, behavior: 'instant' });
      returnTo.current = null;
    }
  }, [selectedMatch]);

  function openMatch(match, event) {
    returnTo.current = { button: event.currentTarget, scrollY: window.scrollY };
    setSelectedMatch(match);
  }

  function searchPlayer(nextIdentity) {
    returnTo.current = null;
    setSelectedMatch(null);
    setGame(nextIdentity.game);
    setRegion(nextIdentity.region);
    setQuery(nextIdentity.name);
    history.search(nextIdentity);
    document.getElementById('main-content')?.focus();
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  function submitSearch(event) {
    event.preventDefault();
    searchPlayer({ game, region, name: query });
  }

  function changeGame(nextGame) {
    if (nextGame === game) return;
    returnTo.current = null;
    setSelectedMatch(null);
    history.reset();
    setGame(nextGame);
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-symbol"><Swords size={24} aria-hidden="true" /></span>
          <div><strong>MATCH<span>UP</span></strong><small>YOUR GAME, IN FOCUS</small></div>
        </div>
        <p className="nav-label">Choose your game</p>
        <nav className="game-nav" aria-label="Game selection">
          <button className={game === 'lol' ? 'nav-item active' : 'nav-item'} aria-pressed={game === 'lol'} onClick={() => changeGame('lol')}>
            <Swords size={20} aria-hidden="true" />
            <span><b>League of Legends</b><small>LOL</small></span>
            <ArrowRight className="nav-arrow" size={15} aria-hidden="true" />
          </button>
          <button className={game === 'tft' ? 'nav-item active' : 'nav-item'} aria-pressed={game === 'tft'} onClick={() => changeGame('tft')}>
            <Shield size={20} aria-hidden="true" />
            <span><b>Teamfight Tactics</b><small>TFT</small></span>
            <ArrowRight className="nav-arrow" size={15} aria-hidden="true" />
          </button>
        </nav>
        <div className="sidebar-note">
          <ChartNoAxesCombined size={22} aria-hidden="true" />
          <p>Every match<br />tells a story.</p>
          <span>Explore your recent performances, one game at a time.</span>
        </div>
        <p className="sidebar-footer">MATCH HISTORY & INSIGHTS</p>
      </aside>

      <main className="content" id="main-content" tabIndex={-1}>
        <header className="topbar">
          <div>
            <p className="eyebrow">Your performance, at a glance</p>
            <h1>{game === 'lol' ? 'League of Legends' : 'Teamfight Tactics'}</h1>
            <p className="page-description">{game === 'lol' ? 'Your matches, your champions, your next move.' : 'Your boards, your placements, your next move.'}</p>
          </div>
          <button className="refresh-button" title="Refresh results" onClick={() => { setSelectedMatch(null); history.refresh(); }} disabled={loading || !identity}>
            <RefreshCw size={16} className={loading && data ? 'spin' : undefined} aria-hidden="true" />
            Refresh
          </button>
        </header>

        <form className="search-panel" onSubmit={submitSearch}>
          <label className="search-id">
            Riot ID
            <span className="input-with-icon">
              <Search size={18} aria-hidden="true" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="GameName#TagLine"
                autoComplete="off"
                spellCheck={false}
                required
              />
            </span>
          </label>
          <label>
            Region
            <span className="input-with-icon">
              <Globe2 size={17} aria-hidden="true" />
              <select value={region} onChange={(event) => setRegion(event.target.value)}>
                {regions.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            </span>
          </label>
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? <LoaderCircle className="spin" size={18} aria-hidden="true" /> : <Search size={18} aria-hidden="true" />}
            {loading ? 'Searching' : 'Search player'}
          </button>
        </form>

        {error ? <div className="error-panel" role="alert">{error}</div> : null}

        <div hidden={Boolean(selectedMatch)}>
        {data ? (
          <>
            <ProfileSummary game={game} profile={data.profile} matches={data.matches} />
            {!selectedMatch && <LiveGame key={`${identity.game}-${identity.region}-${identity.name}`} identity={identity} />}
            {game === 'lol' && <ChampionStats
              key={`${identity.name}-${identity.region}-${data.pagination.asOf}`}
              matches={data.matches} playerName={data.profile.name} />}
            <section className="history-list" aria-label="Match history" aria-busy={loading}>
              <div className="section-heading">
                <div><p className="eyebrow">The latest games</p><h2>Match history <span className="count-badge">{data.matches.length}</span></h2></div>
                <span className="section-caption"><Clock3 size={14} aria-hidden="true" /> Most recent first</span>
              </div>
              {data.matches.length > 0 ? data.matches.map((match) =>
                game === 'lol' ? <LolMatchCard key={match.id} match={match} now={now} onOpen={openMatch} /> : <TftMatchCard key={match.id} match={match} now={now} onOpen={openMatch} />,
              ) : <div className="empty-row">No match history returned.</div>}
              {data.pagination.hasMore ? (
                <button className="secondary-button" disabled={loading} onClick={() => history.loadMore()}>
                  {loading ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
                  {loading ? 'Loading' : 'View more history'}
                </button>
              ) : data.matches.length > 0 ? <p className="history-end" role="status">All available history loaded.</p> : null}
            </section>
          </>
        ) : (
          <EmptyState game={game} loading={loading} />
        )}
        </div>
        {selectedMatch && identity && <MatchDetail key={`${identity.game}-${identity.region}-${identity.name}-${selectedMatch.id}`}
          match={selectedMatch} identity={identity} onBack={() => setSelectedMatch(null)} onProfileSearch={searchPlayer} />}
        <footer className="page-footer"><span>MATCHUP</span> A closer look at your game.</footer>
      </main>
    </div>
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
    <section className="profile-summary" aria-label="Player overview">
      <div className="profile-person">
        <GameImage src={asset(`profileicon/${profile.profileIconId}.png`)} alt="" />
        <div>
          <p className="eyebrow">Player overview</p>
          <h2>{profile.name}</h2>
          <p><span className="level-badge">Lv. {profile.level}</span> {profile.region}</p>
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
          background: summary.percent === null ? 'var(--border)'
            : `conic-gradient(var(--accent) 0 ${summary.percent}%, var(--border) ${summary.percent}% 100%)`,
        }} />
        <div>
          <p className="label">{summary.label}</p>
          <strong className="summary-value">{summary.percent === null ? 'N/A' : `${summary.percent}%`}</strong>
          <p>Across {summary.count} loaded matches</p>
        </div>
      </div>
    </section>
  );
}

export function LolMatchCard({ match, now, onOpen }) {
  const won = match.result === 'Victory';
  const name = championName(match.champion, match.championName);

  return (
    <article className={won ? 'match-card win is-clickable' : 'match-card loss is-clickable'}>
      <button type="button" className="match-open" onClick={(event) => onOpen(match, event)}
        aria-label={`View match details: ${name}, ${match.result}, ${match.queue}, ${formatAge(match.timestamp, now)}`} />
      <div className="match-meta">
        <b className="result-badge">{match.result}</b>
        <strong>{match.queue}</strong>
        <span>
          <Clock3 size={13} aria-hidden="true" />
          {formatAge(match.timestamp, now)}
        </span>
        <span>{match.duration}</span>
      </div>
      <div className="match-performance">
        <div className="champion-block">
          <div className="champion-portrait">
            <GameImage className="champion-icon" src={asset(`champion-icon/${match.champion}.png`)} alt="" />
            <span className="champion-level" title="Champion level">{match.level}</span>
          </div>
          <div className="spell-stack">
            {match.spells.filter(Boolean).map((spell, index) => (
              <GameImage key={`${spell}-${index}`} src={asset(`summonerSpell/${spell}`)} alt="" />
            ))}
          </div>
          <div className="combat-stats">
            <p>{name}</p>
            <h3>{match.kda}</h3>
            <span>{match.ratio}</span>
          </div>
        </div>
        <div className="item-row">
          {match.items.map((item, index) => {
            const label = Number(item) > 0 ? itemName(item) : 'Empty item slot';
            return <GameImage key={`${item}-${index}`} src={asset(`item/${item}.png`)} alt={label} title={label} />;
          })}
        </div>
      </div>
      <ParticipantList match={match} />
      <span className="match-detail-hint" aria-hidden="true">View match details & AI review <ArrowRight size={14} /></span>
    </article>
  );
}

function ParticipantList({ match }) {
  return (
    <div className="participant-grid">
      {[match.teamA, match.teamB].map((team, index) => (
        <div key={index}>
          <p className="team-label">Team {index === 0 ? '1' : '2'}</p>
          {team.map((participant) => (
            <span className="participant" key={`${participant.champion}-${participant.name}`}>
              <GameImage src={asset(`champion-icon/${participant.champion}.png`)} alt="" />
              <span title={participant.name}>{participant.name}</span>
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

export function TftMatchCard({ match, now, onOpen }) {
  const placement = match.placementNumber;
  const resultClass = placement >= 1 && placement <= 8 ? (placement <= 4 ? 'win' : 'loss') : '';
  return (
    <article className={`match-card tft-card is-clickable ${resultClass}`}>
      <button type="button" className="match-open" onClick={(event) => onOpen(match, event)}
        aria-label={`View match details: ${match.placement}, ${match.queue}, ${formatAge(match.timestamp, now)}`} />
      <div className="match-meta">
        <b className="result-badge">{match.placement}</b>
        <strong>{match.queue}</strong>
        <span>
          <Clock3 size={13} aria-hidden="true" />
          {formatAge(match.timestamp, now)}
        </span>
      </div>
      <div className="tft-composition">
        <div className="unit-board">
          {match.units.map((unit, index) => (
            <div className="unit" key={`${match.id}-${index}`}>
              <GameImage src={asset(`tft-champion/${unit.champion}`)} alt="" />
              <span title={unit.name}>{unit.name}</span>
            </div>
          ))}
        </div>
        <div className="trait-row">
          {match.traits.map((trait) => (
            <span key={trait}>
              <Trophy size={13} aria-hidden="true" />
              {trait}
            </span>
          ))}
        </div>
      </div>
      <span className="match-detail-hint" aria-hidden="true">View match details <ArrowRight size={14} /></span>
    </article>
  );
}

function EmptyState({ game, loading }) {
  return (
    <section className="empty-state" aria-label={loading ? 'Searching match history' : 'Get started'}>
      <div className="empty-copy">
        <p className="eyebrow">{loading ? 'Gathering your games' : 'See the bigger picture'}</p>
        <h2>{loading ? 'Your matches are on the way.' : <>Every game.<br /><span>A little more insight.</span></>}</h2>
        <p role={loading ? 'status' : undefined}>{loading ? 'Finding recent matches and preparing your player overview.' : 'Enter your Riot ID and region above to explore your match history and see how you played.'}</p>
        <div className="empty-hint">{loading ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : <ArrowRight size={16} aria-hidden="true" />}
          {loading ? 'Searching match history' : 'Start with GameName#TagLine'}</div>
      </div>
      <div className="empty-art" aria-hidden="true">
        <div className="art-orbit" />
        <GameImage loading="eager" src={asset(game === 'lol' ? 'picture/yasuo.png' : 'picture/TFT.png')} alt="" />
        <span className="art-caption">{game === 'lol' ? 'LEAGUE OF LEGENDS' : 'TEAMFIGHT TACTICS'}</span>
      </div>
      <div className="empty-features">
        <div><Clock3 size={18} aria-hidden="true" /><span><strong>Recent matches</strong><small>Revisit every result</small></span></div>
        <div><ChartNoAxesCombined size={18} aria-hidden="true" /><span><strong>{game === 'lol' ? 'Champion statistics' : 'Board & placement'}</strong><small>{game === 'lol' ? 'Discover your most played' : 'Explore your compositions'}</small></span></div>
        <div>{game === 'lol' ? <Sparkles size={18} aria-hidden="true" /> : <Trophy size={18} aria-hidden="true" />}<span><strong>{game === 'lol' ? 'AI match insights' : 'Top-four rate'}</strong><small>{game === 'lol' ? 'Find your next replay focus' : 'See your recent consistency'}</small></span></div>
      </div>
    </section>
  );
}

export default App;
