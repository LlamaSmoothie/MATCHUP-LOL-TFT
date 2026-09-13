import React from 'react';
import { LoaderCircle } from 'lucide-react';
import AiAnalysis from './AiAnalysis.jsx';
import GameImage from './GameImage.jsx';
import { asset, itemName } from './assets.js';
import { createGameData, validTimeline, formatGameTime } from './gameData.js';

const display = (n) => Number.isFinite(n) ? n.toLocaleString() : 'Unavailable';

export default function MatchTimeline({ request }) {
  const [store] = React.useState(() => createGameData('/api/match-timeline', validTimeline));
  const { data, loading, error } = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const [started, setStarted] = React.useState(false);
  React.useEffect(() => { setStarted(true); store.load(request); return () => store.cancel(); }, [store, request]);
  return <>
    <section className="match-timeline" aria-label="Completed match timeline" aria-busy={loading}>
      <div className="stats-heading"><h3>Match timeline</h3><span className="stats-note">Completed game</span></div>
      {(!started || loading) && <p className="detail-loading" role="status"><LoaderCircle size={18} className="spin" /> Loading timeline…</p>}
      {error && <div role="alert"><p className="ai-error">{error}</p><button className="stats-button" onClick={() => store.load(request)}>Retry timeline</button></div>}
      {data && !data.available && <p className="stats-note">{data.message || 'No timeline samples are available for this match.'}</p>}
      {data?.available && <TimelineContent data={data} />}
    </section>
    <AiAnalysis key={data?.available ? 'with-timeline' : 'summary-only'} request={request} disabled={!started || loading} />
  </>;
}

export function TimelineContent({ data }) {
  const [metric, setMetric] = React.useState('gold');
  const [index, setIndex] = React.useState(0);
  const [category, setCategory] = React.useState('all');
  const [limit, setLimit] = React.useState(30);
  const samples = data.samples;
  const selected = samples[Math.min(index, samples.length - 1)];
  const label = { gold: 'Gold', xp: 'Experience', cs: 'CS', teamGoldDifference: 'Team gold difference' }[metric];
  const opponentKey = { gold: 'opponentGold', xp: 'opponentXp', cs: 'opponentCs' }[metric];
  const opponent = data.participants.find((p) => p.id === data.opponentId);
  const filtered = data.events.filter((e) => category === 'all' || (category === 'combat' ? e.type === 'CHAMPION_KILL'
    : category === 'items' ? e.type.startsWith('ITEM_') : category === 'objectives'
      ? ['BUILDING_KILL', 'ELITE_MONSTER_KILL', 'TURRET_PLATE_DESTROYED'].includes(e.type) : e.type.startsWith('SKILL_') || e.type.startsWith('WARD_')));
  return <>
    <label className="timeline-select">Progression <select value={metric} onChange={(e) => setMetric(e.target.value)}>
      <option value="gold">Gold</option><option value="xp">Experience</option><option value="cs">CS</option><option value="teamGoldDifference">Team gold difference</option>
    </select></label>
    <TimelineChart samples={samples} metric={metric} opponentKey={opponentKey} selectedIndex={index} label={label} />
    {selected && <>
      <label className="timeline-scrubber">Inspect at {formatGameTime(selected.timestamp)}
        <input aria-label="Timeline sample" type="range" min="0" max={Math.max(0, samples.length - 1)} value={Math.min(index, samples.length - 1)}
          onChange={(e) => setIndex(Number(e.target.value))} /></label>
      <dl className="timeline-values"><div><dt>{metric === 'teamGoldDifference' ? 'Your team minus opponents' : `Your ${label.toLowerCase()}`}</dt><dd>{display(selected[metric])}</dd></div>
        {opponentKey && opponent && <div><dt>{opponent.name} · same-role comparison</dt><dd>{display(selected[opponentKey])}</dd></div>}
        <div><dt>Your team gold</dt><dd>{display(selected.teamGold)}</dd></div>
        <div><dt>Opposing team gold</dt><dd>{display(selected.opposingTeamGold)}</dd></div>
      </dl>
    </>}
    <p className="stats-note">Teal: searched player or team difference. Coral: same-role opponent when available.
      Samples follow Riot’s recorded timestamps{data.frameInterval ? ` (nominal spacing ${data.frameInterval / 1000} seconds)` : ''}; gaps are unavailable data.</p>
    <div className="stats-heading"><h4>Recorded events</h4><label className="timeline-select">Show <select value={category} onChange={(e) => { setCategory(e.target.value); setLimit(30); }}>
      <option value="all">All events</option><option value="combat">Kills and deaths</option><option value="objectives">Objectives</option>
      <option value="items">Your item history</option><option value="other">Your skills and wards</option>
    </select></label></div>
    <ol className="timeline-events">{filtered.slice(0, limit).map((event, i) => <li key={`${event.timestamp}-${i}`}>
      <time>{formatGameTime(event.timestamp)}</time><span>{eventText(event, data.participants)}
        {event.involvement && <small>{event.involvement === 'participant' ? 'Your event' : `Your ${event.involvement}`}</small>}</span>
      {event.itemId > 0 && <GameImage src={asset(`item/${event.itemId}.png`)} alt={itemName(event.itemId)} />}
    </li>)}</ol>
    {!filtered.length && <p className="stats-note">No recorded events for this filter.</p>}
    {filtered.length > limit && <button className="stats-button" onClick={() => setLimit(limit + 30)}>Show more events ({filtered.length - limit})</button>}
    <p className="stats-note">Items show recorded purchases, sales, removals and undo actions. Missing or inconsistent Riot events can leave gaps.
      These snapshots and events do not reconstruct a full replay.</p>
  </>;
}

export function TimelineChart({ samples, metric, opponentKey, selectedIndex = 0, label }) {
  const values = samples.flatMap((p) => [p[metric], opponentKey ? p[opponentKey] : null]).filter(Number.isFinite);
  if (!values.length) return <p className="stats-note">No {label.toLowerCase()} samples available.</p>;
  const min = Math.min(0, ...values), max = Math.max(1, ...values), end = Math.max(1, samples.at(-1)?.timestamp || 0);
  const x = (t) => 65 + t / end * 640;
  const y = (v) => 175 - (v - min) / (max - min) * 150;
  const path = (key) => {
    let connected = false;
    return samples.map((p) => {
      if (!Number.isFinite(p[key])) { connected = false; return ''; }
      const segment = `${connected ? 'L' : 'M'}${x(p.timestamp)},${y(p[key])}`;
      connected = true;
      return segment;
    }).join(' ');
  };
  const selected = samples[Math.min(selectedIndex, samples.length - 1)];
  return <svg className="timeline-chart" viewBox="0 0 730 215" role="img" aria-label={`${label} progression; use the sample slider below for exact values`}>
    <line x1="65" y1={y(0)} x2="705" y2={y(0)} className="chart-grid" />
    <text x="6" y="30">{max.toLocaleString()}</text><text x="6" y="180">{min.toLocaleString()}</text>
    <text x="65" y="204">0:00</text><text x="705" y="204" textAnchor="end">{formatGameTime(end)}</text>
    <path d={path(metric)} className="chart-player" />
    {opponentKey && <path d={path(opponentKey)} className="chart-opponent" />}
    {selected && <line x1={x(selected.timestamp)} x2={x(selected.timestamp)} y1="20" y2="175" className="chart-cursor" />}
  </svg>;
}

export function eventText(event, participants) {
  const name = (id) => participants.find((p) => p.id === id)?.name || 'Unknown participant';
  const title = (s) => s?.toLowerCase().replaceAll('_', ' ');
  if (event.type === 'CHAMPION_KILL') return `${name(event.actorId)} → ${name(event.victimId)}`;
  if (event.type.startsWith('ITEM_')) {
    if (event.type === 'ITEM_UNDO') return `Undo purchase/sale (${event.beforeId ? itemName(event.beforeId) : 'unavailable item'} → ${event.afterId ? itemName(event.afterId) : 'none / unavailable'})`;
    return `${{ ITEM_PURCHASED: 'Purchased', ITEM_SOLD: 'Sold', ITEM_DESTROYED: 'Removed' }[event.type]} ${itemName(event.itemId)}`;
  }
  if (event.type === 'SKILL_LEVEL_UP') return `Leveled ${['', 'Q', 'W', 'E', 'R'][event.skillSlot] || 'skill'}`;
  return `${title(event.type)}${event.objective ? ` · ${title(event.objective)}` : ''}`;
}
