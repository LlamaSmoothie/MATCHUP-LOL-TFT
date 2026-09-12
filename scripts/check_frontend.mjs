// Exercise Vite's actual transform and public-file serving without a Riot key.
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { asset } from '../frontend/src/assets.js';
import { championStatistics } from '../frontend/src/championStats.js';

const measureOnly = process.argv.includes('--measure-only');
const server = await createServer({
  configFile: fileURLToPath(new URL('../frontend/vite.config.js', import.meta.url)),
  logLevel: 'silent',
  server: { host: '127.0.0.1', port: 0, open: false },
});

try {
  const started = performance.now();
  const result = await server.transformRequest('/src/assets.js');
  assert.ok(result, 'Vite did not transform the image URL helper.');
  const imageImports = [...result.code.matchAll(/import\s+[^;\n]+\.png[^;\n]+/g)].length;
  console.log(JSON.stringify({
    assetModuleBytes: Buffer.byteLength(result.code),
    startupImageModuleImports: imageImports,
    assetTransformMs: Math.round(performance.now() - started),
  }));
  if (!measureOnly) {
    assert.equal(imageImports, 0, 'Images must not block startup as JavaScript imports.');
    const { default: ChampionStats, ChampionDetails } = await server.ssrLoadModule('/src/ChampionStats.jsx');
    const matches = [{ id: 'fixture', champion: '6', result: 'Victory', kills: 10, deaths: 2, assists: 4,
      queueId: 420, queue: 'Ranked Solo', patch: '16.18', role: 'TOP', finalItems: ['1001'],
      runes: { primary: { style: 8000, perks: [8005] }, secondary: { style: 8400, perks: [8444] } } }];
    const html = renderToStaticMarkup(React.createElement(ChampionStats, { matches, playerName: 'Example#NA1' }));
    for (const text of ['Example#NA1', 'Champion statistics', 'Urgot', '100.0%', '10.0 / 2.0 / 4.0',
      '1 of 1 eligible loaded matches', 'All queues', 'All roles', 'All patches', 'aria-expanded="false"']) {
      assert.ok(html.includes(text), `Missing champion panel content: ${text}`);
    }
    const details = renderToStaticMarkup(React.createElement(ChampionDetails, { row: championStatistics(matches).rows[0] }));
    for (const text of ['Boots', 'Press the Attack', '1/1 games', 'stat shards excluded', asset('rune/8005')]) {
      assert.ok(details.includes(text), `Missing champion detail content: ${text}`);
    }
    const empty = renderToStaticMarkup(React.createElement(ChampionStats, { matches: [], playerName: 'Empty#NA1' }));
    assert.ok(empty.includes('No champion statistics yet.'));
    const { default: AiAnalysis, AnalysisResult } = await server.ssrLoadModule('/src/AiAnalysis.jsx');
    const request = { game: 'lol', region: 'North America', name: 'Example#NA1',
      matchIds: ['fixture'], filters: { queue: '', role: '', patch: '' } };
    const ai = renderToStaticMarkup(React.createElement(AiAnalysis, { request, sampleSize: 1 }));
    assert.ok(ai.includes('Analyze my matches'));
    assert.ok(ai.includes('aggregate statistics are sent to OpenAI'));
    const analysis = { summary: '<script>untrusted</script>', observations: ['One game.'],
      reviewSuggestions: ['Review a replay.'], limitations: ['Small sample.'] };
    const insight = renderToStaticMarkup(React.createElement(AnalysisResult, {
      data: { analysis, sample: { sampleSize: 1, championCount: 1, coveredChampionCount: 1 }, generatedAt: 1000 },
    }));
    assert.ok(insight.includes('&lt;script&gt;untrusted&lt;/script&gt;'));
    assert.ok(!insight.includes('<script>'));
    assert.ok(insight.includes('Questions for your next replay'));
    console.log('PASS: AI analysis renders on demand, labels its sample, and escapes model output.');
    console.log('PASS: champion table, item/rune details, sample labels and empty state render in React.');
    await server.listen();
    const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
    for (const path of ['/picture/TFT.png', '/picture/yasuo.png', '/ranked-emblem/emblem-gold.png']) {
      const response = await fetch(origin + path);
      assert.equal(response.status, 200, `Missing development image: ${path}`);
      assert.match(response.headers.get('content-type'), /^image\/png/);
      await response.arrayBuffer();
    }
    const page = await fetch(origin + '/');
    assert.equal(page.status, 200);
    assert.match(await page.text(), /\/src\/main.jsx/);
    for (const path of ['profileicon/6.png', 'champion-icon/6.png', 'item/1001.png',
      'summonerSpell/SummonerFlash.png', 'rune/8005', 'tft-regalia/GOLD']) {
      assert.equal(new URL(asset(path)).origin, 'https://ddragon.leagueoflegends.com');
    }
    const removed = await fetch(origin + '/profileicon/6.png');
    assert.ok(!removed.headers.get('content-type')?.startsWith('image/'), 'Old images are still served locally.');
    console.log('PASS: local UI art is served; game images use Riot CDN without startup image imports.');
  }
} finally {
  await server.close();
}
