// Optional live check: only public images, no backend or Riot API key required.
import assert from 'node:assert/strict';
import { asset, assetVersion } from '../frontend/src/assets.js';
import catalog from '../frontend/src/riot-assets.json' with { type: 'json' };

const tftUnit = Object.keys(catalog.tftChampions).find((id) => /^TFT\d+_/.test(id));
assert.ok(tftUnit, 'No regular TFT unit is in the pinned metadata.');
const paths = ['profileicon/6.png', 'champion-icon/6.png', 'item/1001.png',
  'summonerSpell/SummonerFlash.png', `tft-champion/${tftUnit}`,
  'tft-regalia/GOLD', 'tft-regalia/GRANDMASTER', 'tft-regalia/PROVISIONAL'];
for (const path of paths) {
  const url = asset(path);
  assert.equal(new URL(url).origin, 'https://ddragon.leagueoflegends.com');
  const response = await fetch(url, { signal: AbortSignal.timeout(15000), credentials: 'omit' });
  assert.equal(response.status, 200, `Missing CDN image: ${url}`);
  assert.match(response.headers.get('content-type'), /^image\/png/);
  const body = Buffer.from(await response.arrayBuffer());
  assert.equal(body.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  console.log(`PASS: ${path}`);
}
console.log(`PASS: Data Dragon ${assetVersion} serves all ${paths.length} representative images.`);
