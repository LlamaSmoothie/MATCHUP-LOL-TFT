import React from 'react';
import GameImage from './GameImage.jsx';
import { asset, championName } from './assets.js';
import { createLiveProfiles } from './liveProfiles.js';

const average = (n) => Number.isFinite(n) ? n.toFixed(1) : '—';

export default function LiveRoster({ identity, game, gameId, participants = [] }) {
  const [store] = React.useState(createLiveProfiles);
  const state = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const rosterKey = JSON.stringify(participants.map((p) => [p.index, p.name, p.canLoadProfile]));
  const request = { ...identity, gameId };
  React.useEffect(() => {
    // Allow React's development effect cleanup to cancel before issuing requests.
    const timer = setTimeout(() => {
      if (game === 'lol' && identity) store.load({ ...identity, gameId }, participants);
    }, 0);
    return () => { clearTimeout(timer); store.cancel(); };
  }, [store, identity, game, gameId, rosterKey]);
  return <div className="live-profiles">
    {game === 'lol' && <>
      <div className="stats-heading"><h4>Player profiles</h4>
        {identity && <button className="stats-button" disabled={state.loading} onClick={() => store.load(request, participants)}>Retry player stats</button>}</div>
      <p className="stats-note">Ranks are current Solo/Duo and Flex standings. Most played and average KDA use up to 20 recent completed matches across queues, including ARAM; custom games are excluded.</p>
      {state.loading && <p className="stats-note" role="status">Loading player stats… {Object.keys(state.rows).length} / {participants.filter((p) => p.canLoadProfile).length}</p>}
      {state.error && <p className="ai-error" role="alert">{state.error}</p>}
    </>}
    <div className="live-roster">{participants.map((player, i) => <article key={player.index ?? i} className={player.isSearchedPlayer ? 'current-player' : undefined}>
      <div className="live-player-heading">
        {game === 'lol' && <GameImage src={asset(`champion-icon/${player.champion}.png`)} alt="" />}
        <span><strong>{player.name}</strong><small>{game === 'lol' ? championName(player.champion) : 'TFT participant'}
          {player.teamId === 100 ? ' · Blue team' : player.teamId === 200 ? ' · Red team' : ''}</small></span>
      </div>
      {game === 'lol' && <PlayerHistory row={state.rows[player.index]} canLoad={player.canLoadProfile} loading={state.loading} />}
    </article>)}</div>
  </div>;
}

export function PlayerHistory({ row, canLoad = true, loading = false }) {
  if (!canLoad) return <p className="stats-note">Profile statistics unavailable for this participant.</p>;
  if (row?.error) return <p className="ai-error">{row.error}</p>;
  if (!row?.data) return <p className="stats-note">{loading ? 'Waiting for player stats…' : 'Player stats not loaded.'}</p>;
  const { rank, history } = row.data;
  return <dl className="live-player-stats">
    <div><dt>Rank</dt><dd>{rank.status === 'ready' ? rank.queues.map((q) => <span key={q.queue} className="live-rank">
      <small>{q.queue}</small>{q.status === 'unranked' ? 'Unranked' : q.status === 'unavailable' ? 'Unavailable'
        : `${q.tier[0]}${q.tier.slice(1).toLowerCase()} ${['MASTER', 'GRANDMASTER', 'CHALLENGER'].includes(q.tier) ? '' : q.division + ' · '}${q.lp} LP`}
    </span>) : <span>Unavailable<small>{rank.message}</small></span>}</dd></div>
    {history.status !== 'ready' ? <div><dt>Recent history</dt><dd>Unavailable<small>{history.message}</small></dd></div> : <>
      <div><dt>Most played · recent matches</dt><dd>{history.mostPlayed ? <span className="live-most-played">
        <GameImage src={asset(`champion-icon/${history.mostPlayed.champion}.png`)} alt="" />
        <span>{championName(history.mostPlayed.champion)}<small>{history.mostPlayed.games} / {history.sampleSize} games</small></span>
      </span> : 'No eligible matches'}</dd></div>
      <div><dt>Average K / D / A · recent matches</dt><dd>{history.sampleSize ? <>
        <span>{[history.averageKills, history.averageDeaths, history.averageAssists].map(average).join(' / ')}</span>
        <small>{history.deathless ? 'Deathless sample' : `${history.kda?.toFixed(2) ?? '—'} KDA ratio`} · {history.sampleSize} games</small>
      </> : 'No eligible matches'}</dd></div>
      <div className="live-sample"><dt>Sample</dt><dd>{history.sampleSize} eligible of {history.requestedMatches} retrieved matches</dd></div>
    </>}
  </dl>;
}
