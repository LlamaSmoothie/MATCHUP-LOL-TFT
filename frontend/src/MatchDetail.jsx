import React from 'react';
import { ArrowLeft, ArrowUpRight, LoaderCircle } from 'lucide-react';
import { asset, championName, itemName } from './assets.js';
import GameImage from './GameImage.jsx';
import MatchTimeline from './MatchTimeline.jsx';
import MatchStatistics from './MatchStatistics.jsx';
import { createMatchDetails, detailRequest } from './matchDetails.js';

const value = (n) => Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';

export default function MatchDetail({ match, identity, onBack, onProfileSearch }) {
  const [store] = React.useState(() => createMatchDetails());
  const state = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const request = React.useMemo(() => detailRequest(identity, match), [identity.game, identity.region, identity.name, match.id]);
  const heading = React.useRef(null);
  React.useEffect(() => {
    store.load(request);
    return () => store.cancel();
  }, [store, request]);
  React.useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView({ block: 'start' });
  }, []);

  async function searchParticipant(index) {
    const target = await store.profile(index);
    if (target) onProfileSearch(target);
  }

  return <section className="match-detail" aria-labelledby="match-detail-title" aria-busy={state.loading}>
    <button type="button" className="stats-button" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" /> Back to match history</button>
    <header className="detail-heading">
      <div>
        <p className="eyebrow">{match.queue} · {identity.name}</p>
        <h2 id="match-detail-title" ref={heading} tabIndex={-1}>Match details</h2>
        <p className="stats-note">{match.result || match.placement}{match.duration ? ` · ${match.duration}` : ''}</p>
      </div>
    </header>
    {state.loading && <p className="detail-loading" role="status"><LoaderCircle className="spin" size={18} aria-hidden="true" /> Loading match statistics…</p>}
    {state.error && <div className="error-panel" role="alert"><p>{state.error}</p>
      <button className="stats-button" onClick={() => store.load(request)}>Retry match details</button></div>}
    {state.profileLoading !== null && <p role="status">Opening player profile…</p>}
    {state.profileError && <p className="error-panel" role="alert">{state.profileError}</p>}
    {state.data && <MatchDetailContent data={state.data} request={request} onProfileSearch={searchParticipant}
      profileLoading={state.profileLoading} />}
  </section>;
}

export function MatchDetailContent({ data, request, onProfileSearch, profileLoading = null }) {
  const profileButton = (player) => <button type="button" className="player-profile-link"
    onClick={() => onProfileSearch(player.index)} disabled={!player.canSearch || profileLoading !== null}
    title={player.canSearch ? `Search ${player.name}'s profile` : 'Profile unavailable in this match record'}>
    <span>{player.name}{player.isSearchedPlayer && <small>Current player</small>}</span>
    {player.canSearch && <ArrowUpRight size={14} aria-hidden="true" />}
  </button>;

  return <>
    <section className="match-scoreboard" aria-label="Participant statistics">
      <div className="stats-heading"><h3>Scoreboard</h3><span className="stats-note">{data.participants.length} participants</span></div>
      <p className="stats-note">Select a player name to search their profile. A dash means the statistic is unavailable.</p>
      {data.game === 'lol' ? <LolScoreboard participants={data.participants} profileButton={profileButton} />
        : <TftScoreboard participants={data.participants} profileButton={profileButton} />}
    </section>
    {data.game === 'lol' && <>
      <p className="detail-player-label">Statistics and AI review for <strong>{data.playerName}</strong></p>
      <MatchStatistics match={data.match} />
      <MatchTimeline key={JSON.stringify(request)} request={request} />
    </>}
  </>;
}

function LolScoreboard({ participants, profileButton }) {
  const groups = new Map();
  for (const player of participants) {
    const key = player.teamId ?? 'unknown';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(player);
  }
  return [...groups].map(([teamId, players], index) => <div key={teamId} className="scoreboard-team">
    <h4>{teamId === 'unknown' ? 'Team unavailable' : `Team ${index + 1}`} <span className={players[0].result === 'Victory' ? 'win-text' : 'loss-text'}>{players[0].result}</span></h4>
    <div className="scoreboard-scroll" tabIndex={0} role="region" aria-label={`Team ${index + 1} statistics`}>
      <table className="scoreboard-table"><thead><tr>
        {['Player', 'Champion', 'K / D / A', 'CS', 'Gold', 'Damage', 'Vision', 'Final items'].map((text) => <th key={text} scope="col">{text}</th>)}
      </tr></thead><tbody>{players.map((player) => {
        const { combat = {}, economy = {}, vision = {} } = player.statistics || {};
        const name = championName(player.champion, player.championName);
        return <tr key={player.index} className={player.isSearchedPlayer ? 'current-player' : undefined}>
          <th scope="row">{profileButton(player)}</th>
          <td><span className="scoreboard-champion"><GameImage src={asset(`champion-icon/${player.champion}.png`)} alt="" />
            <span>{name}<small>{player.role}</small></span></span></td>
          <td className="scoreboard-kda">{[combat.kills, combat.deaths, combat.assists].map(value).join(' / ')}</td>
          <td>{value(economy.totalCS)}<small>{value(economy.csPerMinute)} / min</small></td>
          <td>{value(economy.goldEarned)}</td><td>{value(combat.damageToChampions)}</td><td>{value(vision.score)}</td>
          <td><div className="scoreboard-items">{(player.items || []).map((item, itemIndex) => <GameImage
            key={`${item}-${itemIndex}`} src={asset(`item/${item}.png`)} alt={itemName(item)} title={itemName(item)} />)}</div></td>
        </tr>;
      })}</tbody></table>
    </div>
  </div>);
}

function TftScoreboard({ participants, profileButton }) {
  const players = [...participants].sort((a, b) => (a.placement || Infinity) - (b.placement || Infinity));
  return <div className="scoreboard-scroll" tabIndex={0} role="region" aria-label="TFT placement statistics">
    <table className="scoreboard-table"><thead><tr>
      {['Place', 'Player', 'Level', 'Gold left', 'Last round', 'Players eliminated', 'Player damage', 'Board'].map((text) => <th key={text} scope="col">{text}</th>)}
    </tr></thead><tbody>{players.map((player) => <tr key={player.index} className={player.isSearchedPlayer ? 'current-player' : undefined}>
      <td>{value(player.placement)}</td><th scope="row">{profileButton(player)}</th><td>{value(player.level)}</td>
      <td>{value(player.goldLeft)}</td><td>{value(player.lastRound)}</td><td>{value(player.playersEliminated)}</td><td>{value(player.damageToPlayers)}</td>
      <td><details className="scoreboard-board"><summary>View board</summary><div className="unit-board">
        {(player.units || []).map((unit, index) => <div className="unit" key={index}>
          <GameImage src={asset(`tft-champion/${unit.champion}`)} alt="" />
          <span>{unit.name} · {value(unit.stars)}★</span>
        </div>)}
      </div></details></td>
    </tr>)}</tbody></table>
  </div>;
}
