import catalog from './riot-assets.json' with { type: 'json' };

// A small checked-in map avoids any metadata request during startup or builds.
export const assetVersion = catalog.version;
export const championName = (id, fallback) => catalog.championNames?.[id] || fallback || `Champion ${id}`;
export const itemName = (id) => catalog.itemNames?.[id] || `Item ${id}`;
export const runeName = (id) => catalog.runes?.[id]?.name || `Rune ${id}`;
const cdn = `https://ddragon.leagueoflegends.com/cdn/${assetVersion}/img`;
const fallbackPath = 'picture/TFT.png';
const localRanks = new Set(['iron', 'bronze', 'silver', 'gold', 'platinum', 'diamond',
  'master', 'grandmaster', 'challenger'].map((tier) => `emblem-${tier}.png`));

function mappedImage(group, mapping, id) {
  return Object.hasOwn(mapping, id) ? `${cdn}/${group}/${encodeURIComponent(mapping[id])}` : null;
}

export function asset(path, base = import.meta.env?.BASE_URL || '/') {
  const local = (name) => `${base.replace(/\/$/, '')}/${name}`;
  if (typeof path !== 'string') return local(fallbackPath);
  const [group, filename, ...extra] = path.split('/');
  if (!filename || extra.length) return local(fallbackPath);
  const id = filename.replace(/\.png$/, '');
  let remote;
  if (group === 'picture' && ['TFT.png', 'yasuo.png'].includes(filename)) return local(path);
  if (group === 'ranked-emblem' && localRanks.has(filename)) return local(path);
  if (['profileicon', 'item'].includes(group) && /^\d+\.png$/.test(filename)) {
    remote = `${cdn}/${group}/${filename}`;
  } else if (group === 'summonerSpell' && /^[A-Za-z0-9_]+\.png$/.test(filename)) {
    remote = `${cdn}/spell/${filename}`;
  } else if (group === 'champion-icon') {
    remote = mappedImage('champion', catalog.champions, id);
  } else if (group === 'tft-champion') {
    remote = mappedImage('tft-champion', catalog.tftChampions, id);
  } else if (group === 'tft-regalia') {
    remote = mappedImage('tft-regalia', catalog.tftRegalia, id.toUpperCase());
  } else if (group === 'rune' && Object.hasOwn(catalog.runes || {}, id)) {
    remote = `https://ddragon.leagueoflegends.com/cdn/img/${catalog.runes[id].icon}`;
  }
  return remote || local(fallbackPath);
}

export function fallbackImage(event) {
  const image = event.currentTarget;
  const fallback = asset(fallbackPath);
  // A missing fallback must not create a loop of failed image requests.
  if (image.getAttribute('src') !== fallback) image.setAttribute('src', fallback);
}
