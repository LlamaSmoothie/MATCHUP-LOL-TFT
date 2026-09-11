import test from 'node:test';
import assert from 'node:assert/strict';
import { asset, assetVersion, fallbackImage } from '../../frontend/src/assets.js';
import catalog from '../../frontend/src/riot-assets.json' with { type: 'json' };

const cdn = `https://ddragon.leagueoflegends.com/cdn/${assetVersion}/img`;

test('numeric profile/item IDs and summoner spells resolve directly to the pinned CDN', () => {
  assert.equal(asset('profileicon/6.png'), `${cdn}/profileicon/6.png`);
  assert.equal(asset('item/1001.png'), `${cdn}/item/1001.png`);
  assert.equal(asset('summonerSpell/SummonerFlash.png'), `${cdn}/spell/SummonerFlash.png`);
});

test('numeric LoL IDs map to CDN champion filenames', () => {
  assert.equal(asset('champion-icon/6.png'), `${cdn}/champion/Urgot.png`);
  assert.equal(asset('champion-icon/266.png'), `${cdn}/champion/Aatrox.png`);
});

test('TFT uses character IDs and the exact case of Riot regalia filenames', () => {
  assert.equal(asset('tft-champion/TFTTutorial_Zed'), `${cdn}/tft-champion/TFTTutorial_Zed.png`);
  assert.equal(asset('tft-regalia/GRANDMASTER'), `${cdn}/tft-regalia/TFT_Regalia_GrandMaster.png`);
  assert.equal(asset('tft-regalia/PROVISIONAL'), `${cdn}/tft-regalia/TFT_Regalia_Provisional.png`);
  for (const [id, filename] of Object.entries(catalog.tftChampions)) {
    assert.equal(asset(`tft-champion/${id}`), `${cdn}/tft-champion/${encodeURIComponent(filename)}`);
  }
});

test('local branding/ranks respect deployment paths while CDN URLs stay absolute', () => {
  assert.equal(asset('picture/TFT.png', '/app/'), '/app/picture/TFT.png');
  assert.equal(asset('picture/yasuo.png', '/app'), '/app/picture/yasuo.png');
  assert.equal(asset('ranked-emblem/emblem-gold.png'), '/ranked-emblem/emblem-gold.png');
  assert.equal(asset('profileicon/6.png', '/app/'), `${cdn}/profileicon/6.png`);
});

test('unknown or malformed assets use a local fallback without a metadata fetch', () => {
  for (const path of [null, '', 'champion-icon/999999.png', 'champion-icon/TFT13_Vi.png',
    'tft-champion/Unknown', 'tft-regalia/Unknown', 'ranked-emblem/emblem-n/a.png',
    'picture/other.png', 'item/../../config.env', 'champion-icon/__proto__.png']) {
    assert.equal(asset(path, '/app/'), '/app/picture/TFT.png');
  }
});

test('missing images fall back once and can recover after their source changes', () => {
  let src = asset('item/999999.png');
  let writes = 0;
  const event = { currentTarget: {
    getAttribute: () => src,
    setAttribute: (name, value) => { assert.equal(name, 'src'); src = value; writes++; },
  } };
  fallbackImage(event);
  assert.equal(src, '/picture/TFT.png');
  fallbackImage(event);
  assert.equal(writes, 1);
  src = asset('profileicon/999999.png');
  fallbackImage(event);
  assert.equal(writes, 2);
});
