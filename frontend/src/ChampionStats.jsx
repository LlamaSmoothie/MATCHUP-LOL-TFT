import React from 'react';
import GameImage from './GameImage.jsx';
import { asset, assetVersion, itemName, runeName } from './assets.js';
import { championFilterOptions, championStatistics } from './championStats.js';
import AiAnalysis from './AiAnalysis.jsx';
import { analysisRequest } from './analysis.js';

const emptyFilters = { queue: '', role: '', patch: '' };
const percent = (value) => `${value.toFixed(1)}%`;

export default function ChampionStats({ matches, playerName, identity, historyLoading }) {
  const [filters, setFilters] = React.useState(emptyFilters);
  const [expanded, setExpanded] = React.useState(null);
  const [showAll, setShowAll] = React.useState(false);
  const panelId = React.useId();
  const options = React.useMemo(() => championFilterOptions(matches), [matches]);
  const stats = React.useMemo(() => championStatistics(matches, filters), [matches, filters]);
  const visibleRows = showAll ? stats.rows : stats.rows.slice(0, 1);
  const request = React.useMemo(() => identity && analysisRequest(identity, matches, filters), [identity, matches, filters]);

  function changeFilter(key, value) {
    setFilters((previous) => ({ ...previous, [key]: value }));
    setExpanded(null);
    setShowAll(false);
  }

  return (
    <section className="champion-stats" aria-labelledby={`${panelId}-title`}>
      <div className="stats-heading">
        <div>
          <p className="eyebrow">{playerName}</p>
          <h2 id={`${panelId}-title`}>Champion statistics</h2>
        </div>
        <span className="stats-sample" role="status">{stats.sampleSize} of {stats.eligibleCount} eligible loaded matches</span>
      </div>
      <p className="stats-note" id={`${panelId}-sample`}>
        Based on this player’s loaded history. Load more history below to expand the sample.
        Personal pick share is the percentage of filtered matches played on each champion.
      </p>
      <div className="stats-filters">
        {['queue', 'role', 'patch'].map((key) => (
          <label key={key}>
            {key[0].toUpperCase() + key.slice(1)}
            <select value={filters[key]} onChange={(event) => changeFilter(key, event.target.value)}>
              <option value="">All {key === 'patch' ? 'patches' : `${key}s`}</option>
              {options[key].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
        ))}
        <button className="stats-button" disabled={!Object.values(filters).some(Boolean)}
          onClick={() => { setFilters(emptyFilters); setExpanded(null); setShowAll(false); }}>Clear filters</button>
      </div>
      {stats.rows.length ? (
        <div className="stats-table-scroll" tabIndex={0} role="region" aria-label="Champion statistics table">
          <table className="stats-table" aria-describedby={`${panelId}-sample`}>
            <thead><tr>
              <th scope="col">Champion</th><th scope="col">Games</th><th scope="col">W / L</th>
              <th scope="col">Win rate</th><th scope="col">Personal pick share</th>
              <th scope="col">Average K / D / A</th><th scope="col">Details</th>
            </tr></thead>
            <tbody id={`${panelId}-rows`}>{visibleRows.map((row) => {
              const open = expanded === row.id;
              const detailId = `${panelId}-champion-${row.id}`;
              return <React.Fragment key={row.id}>
                <tr>
                  <th scope="row"><span className="stats-champion">
                    <GameImage src={asset(`champion-icon/${row.id}.png`)} alt="" />{row.name}
                  </span></th>
                  <td>{row.games}</td><td>{row.wins} / {row.losses}</td>
                  <td>{percent(row.winRate)}</td><td>{percent(row.pickShare)}</td>
                  <td>{row.averages ? <>
                    {row.averages.map((n) => n.toFixed(1)).join(' / ')}
                    <small>{row.deathless ? 'Perfect KDA (no deaths)' : `${row.kdaRatio.toFixed(2)} KDA`}</small>
                    {row.combatGames < row.games && <small>KDA data: {row.combatGames}/{row.games} games</small>}
                  </> : 'Unavailable'}</td>
                  <td><button className="stats-button" aria-expanded={open} aria-controls={detailId}
                    aria-label={`${open ? 'Hide' : 'Show'} items and runes for ${row.name}`}
                    onClick={() => setExpanded(open ? null : row.id)}>{open ? 'Hide' : 'Items & runes'}</button></td>
                </tr>
                <tr id={detailId} hidden={!open} className="stats-detail-row">
                  <td colSpan={7}>{open && <ChampionDetails row={row} />}</td>
                </tr>
              </React.Fragment>;
            })}</tbody>
          </table>
        </div>
      ) : <p className="empty-row">{stats.eligibleCount
        ? 'No matches for these filters. Clear filters to see all loaded champions.'
        : 'No champion statistics yet. Search a player with LoL match history.'}</p>}
      {stats.rows.length > 1 && <div className="stats-expand">
        <span className="stats-note">Showing {visibleRows.length} of {stats.rows.length} champions · Most played first</span>
        <button type="button" className="stats-button" aria-expanded={showAll} aria-controls={`${panelId}-rows`}
          onClick={() => {
            if (showAll && expanded !== stats.rows[0].id) setExpanded(null);
            setShowAll(!showAll);
          }}>
          {showAll ? 'Show less' : `Show ${stats.rows.length - 1} more champion${stats.rows.length === 2 ? '' : 's'}`}
        </button>
      </div>}
      <p className="stats-note stats-footer">Small samples can vary widely. Filters affect this table only; these are not lifetime or global rates.</p>
      {request && <AiAnalysis key={JSON.stringify(request)} request={request}
        sampleSize={stats.sampleSize} historyLoading={historyLoading} />}
    </section>
  );
}

export function ChampionDetails({ row }) {
  return <div className="stats-details">
    <div>
      <h3>Most frequent final items</h3>
      <p className="stats-note">Inventory data: {row.itemGames}/{row.games} games. Top 6 items, counted once per game;
        trinkets excluded. This is not purchase order or a recommended build.</p>
      {row.items.length ? <ul className="stats-item-list">{row.items.slice(0, 6).map((item) => <li key={item.id}>
        <GameImage src={asset(`item/${item.id}.png`)} alt="" />
        <span>{itemName(item.id)}<small>{item.games}/{row.itemGames} games ({percent(item.games / row.itemGames * 100)})</small></span>
      </li>)}</ul> : <p>{row.itemGames ? 'No final items recorded.' : 'Item data unavailable.'}</p>}
    </div>
    <div>
      <h3>Most frequent rune selections</h3>
      <p className="stats-note">Rune data: {row.runeGames}/{row.games} games. Top 3 combinations of primary and secondary runes;
        stat shards excluded.</p>
      {row.runes.length ? <ol className="stats-rune-list">{row.runes.slice(0, 3).map((runes) => <li key={runes.key}>
        <strong>{runes.games}/{row.runeGames} games ({percent(runes.games / row.runeGames * 100)})</strong>
        {['primary', 'secondary'].map((key) => <div key={key}>
          <small>{key === 'primary' ? 'Primary' : 'Secondary'}: {runeName(runes[key].style)}</small>
          <div className="stats-runes">{runes[key].perks.map((id) => <span key={id}>
            <GameImage src={asset(`rune/${id}`)} alt="" />{runeName(id)}
          </span>)}</div>
        </div>)}
      </li>)}</ol> : <p>Rune data unavailable.</p>}
    </div>
    <p className="stats-note stats-metadata">Names and artwork use Data Dragon {assetVersion}; older items or runes may show their IDs.</p>
  </div>;
}
