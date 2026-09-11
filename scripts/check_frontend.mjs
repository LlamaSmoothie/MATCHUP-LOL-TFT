// Exercise Vite's actual transform and public-file serving without a Riot key.
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { asset } from '../frontend/src/assets.js';

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
      'summonerSpell/SummonerFlash.png', 'tft-regalia/GOLD']) {
      assert.equal(new URL(asset(path)).origin, 'https://ddragon.leagueoflegends.com');
    }
    const removed = await fetch(origin + '/profileicon/6.png');
    assert.ok(!removed.headers.get('content-type')?.startsWith('image/'), 'Old images are still served locally.');
    console.log('PASS: local UI art is served; game images use Riot CDN without startup image imports.');
  }
} finally {
  await server.close();
}
