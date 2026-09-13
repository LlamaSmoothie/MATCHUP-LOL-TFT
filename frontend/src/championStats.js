import { championName } from './assets.js';

export const roleLabels = { TOP: 'Top', JUNGLE: 'Jungle', MIDDLE: 'Mid', BOTTOM: 'Bot',
  UTILITY: 'Support', UNKNOWN: 'Unknown' };

const dimensions = (match) => ({
  queue: match.queueId == null ? 'unknown' : String(match.queueId),
  role: Object.hasOwn(roleLabels, match.role) ? match.role : 'UNKNOWN',
  patch: match.patch || 'Unknown',
});

function eligibleMatches(matches) {
  // The last copy wins, just as in the paginated history store.
  return [...new Map(matches.filter((m) => m?.id).map((m) => [m.id, m])).values()]
    .filter((m) => /^\d+$/.test(String(m.champion)) && Number(m.champion) > 0
      && ['Victory', 'Defeat'].includes(m.result));
}

export function championFilterOptions(matches) {
  const options = { queue: new Map(), role: new Map(), patch: new Map() };
  for (const match of eligibleMatches(matches)) {
    const values = dimensions(match);
    options.queue.set(values.queue, match.queue || 'Unknown queue');
    options.role.set(values.role, roleLabels[values.role]);
    options.patch.set(values.patch, values.patch);
  }
  return Object.fromEntries(Object.entries(options).map(([key, values]) => [key,
    [...values].sort((a, b) => key === 'patch'
      ? b[0].localeCompare(a[0], undefined, { numeric: true }) : a[1].localeCompare(b[1])),
  ]));
}

function runeSelection(runes) {
  const result = {};
  for (const key of ['primary', 'secondary']) {
    const style = runes?.[key];
    if (!Number.isInteger(style?.style) || style.style <= 0 || !Array.isArray(style.perks)
      || !style.perks.length || style.perks.some((id) => !Number.isInteger(id) || id <= 0)) return null;
    result[key] = { style: style.style, perks: [...style.perks].sort((a, b) => a - b) };
  }
  return result;
}

export function championStatistics(matches, filters = {}) {
  const eligible = eligibleMatches(matches);
  const selected = eligible.filter((match) => Object.entries(dimensions(match))
    .every(([key, value]) => !filters[key] || filters[key] === value));
  const champions = new Map();
  for (const match of selected) {
    const id = String(match.champion);
    if (!champions.has(id)) champions.set(id, {
      id, name: championName(id, match.championName), games: 0, wins: 0,
      kills: 0, deaths: 0, assists: 0, combatGames: 0, itemGames: 0, runeGames: 0,
      items: new Map(), runes: new Map(),
    });
    const row = champions.get(id);
    row.games += 1;
    row.wins += Number(match.result === 'Victory');
    if (['kills', 'deaths', 'assists'].every((key) => Number.isInteger(match[key]) && match[key] >= 0)) {
      row.combatGames += 1;
      for (const key of ['kills', 'deaths', 'assists']) row[key] += match[key];
    }
    if (Array.isArray(match.finalItems)) {
      row.itemGames += 1;
      for (const item of new Set(match.finalItems.map(String).filter((id) => /^\d+$/.test(id) && Number(id) > 0))) {
        row.items.set(item, (row.items.get(item) || 0) + 1);
      }
    }
    const runes = runeSelection(match.runes);
    if (runes) {
      row.runeGames += 1;
      const key = JSON.stringify(runes);
      const usage = row.runes.get(key) || { key, ...runes, games: 0 };
      usage.games += 1;
      row.runes.set(key, usage);
    }
  }
  const rows = [...champions.values()].map((row) => ({
    ...row, losses: row.games - row.wins, winRate: row.wins / row.games * 100,
    pickShare: row.games / selected.length * 100,
    averages: row.combatGames ? [row.kills, row.deaths, row.assists].map((n) => n / row.combatGames) : null,
    kdaRatio: row.combatGames && row.deaths ? (row.kills + row.assists) / row.deaths : null,
    deathless: row.combatGames > 0 && row.deaths === 0,
    items: [...row.items].map(([id, games]) => ({ id, games }))
      .sort((a, b) => b.games - a.games || Number(a.id) - Number(b.id)),
    runes: [...row.runes.values()].sort((a, b) => b.games - a.games || a.key.localeCompare(b.key)),
  })).sort((a, b) => b.games - a.games || b.wins - a.wins || a.name.localeCompare(b.name));
  return { rows, sampleSize: selected.length, eligibleCount: eligible.length };
}
