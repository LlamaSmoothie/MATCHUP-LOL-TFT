import React from 'react';
import { Radio, RefreshCw } from 'lucide-react';
import { createGameData, validLiveGame, formatGameTime } from './gameData.js';
import { asset, itemName } from './assets.js';
import GameImage from './GameImage.jsx';
import LiveRoster from './LiveRoster.jsx';

const value = (n) => Number.isFinite(n) ? n.toLocaleString() : '—';

export default function LiveGame({ identity }) {
  const [store] = React.useState(() => createGameData('/api/live-game', validLiveGame));
  const state = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const [paused, setPaused] = React.useState(false);
  const [started, setStarted] = React.useState(false);
  React.useEffect(() => {
    setStarted(false);
    const update = () => {
      setPaused(document.hidden);
      if (document.hidden) { store.cancel(); setStarted(false); }
    };
    update();
    document.addEventListener('visibilitychange', update);
    return () => { store.cancel(); document.removeEventListener('visibilitychange', update); };
  }, [store, identity]);
  return <section className="live-game" aria-label="Ongoing game" aria-busy={started && state.loading}>
    <div className="stats-heading"><h3><Radio size={18} aria-hidden="true" /> Ongoing game</h3>
      <button className="stats-button" disabled={(started && state.loading) || paused} onClick={() => { setStarted(true); store.load(identity); }}><RefreshCw size={14} /> {started ? 'Check again' : 'Check ongoing game'}</button></div>
    {paused ? <p className="stats-note">Live updates stopped while this tab is hidden. Check again to resume.</p>
      : !started ? <p className="stats-note">Click Check ongoing game to look for an active match. Live updates start only if one is found.</p> : state.loading
      ? <p className="stats-note" role="status">Checking whether this player is in a game…</p>
      : state.error ? <p className="ai-error" role="alert">{state.error}</p>
        : state.data && <LiveGameContent data={state.data} identity={identity} />}
  </section>;
}

export function LiveGameContent({ data, identity }) {
  if (!data.active) return <p className="stats-note">{data.local?.message || data.message} Automatic tracking is stopped.</p>;
  const seconds = data.local.status === 'connected' ? data.local.gameTime : data.gameLength;
  return <>
    <p className="live-heading"><span className="live-badge">IN GAME</span> {data.queue}
      <span>{formatGameTime(Number.isFinite(seconds) ? seconds * 1000 : null)}</span></p>
    <p className="stats-note">Updates every {data.pollAfter} seconds while this page is visible. Last checked {new Date(data.checkedAt * 1000).toLocaleTimeString()}.</p>
    <LiveRoster key={data.gameId} identity={identity} game={data.game} gameId={data.gameId} participants={data.participants} />
    {data.local.status === 'connected' ? <>
      <div className="scoreboard-scroll" tabIndex={0} role="region" aria-label="Live player statistics">
        <table className="scoreboard-table"><thead><tr>{['Player', 'Champion', 'Team', 'Level', 'K / D / A', 'CS', 'Vision', 'Items'].map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
          <tbody>{data.local.players.map((p, i) => <tr key={i} className={p.isSearchedPlayer ? 'current-player' : undefined}>
            <th scope="row">{p.name}</th><td>{p.championName}</td><td>{p.team}</td><td>{value(p.level)}</td>
            <td className="scoreboard-kda">{[p.kills, p.deaths, p.assists].map(value).join(' / ')}</td><td>{value(p.cs)}</td><td>{value(p.vision)}</td>
            <td><div className="scoreboard-items">{p.items.map((item, j) => <GameImage key={j} src={asset(`item/${item}.png`)} alt={itemName(item)} title={itemName(item)} />)}</div></td>
          </tr>)}</tbody></table>
      </div>
      <details className="live-events"><summary>Recent game events</summary><ol className="timeline-events">{data.local.events.map((e, i) => <li key={i}>
        <time>{formatGameTime(e.time === null ? null : e.time * 1000)}</time><span>{e.type.replace(/([a-z])([A-Z])/g, '$1 $2')}</span>
      </li>)}</ol></details>
    </> : <p className="stats-note">{data.local.message}</p>}
  </>;
}
