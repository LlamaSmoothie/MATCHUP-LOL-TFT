// Exercise Vite's actual transform and public-file serving without a Riot key.
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

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
    for (const path of ['/picture/TFT.png', '/picture/yasuo.png', '/profileicon/6.png',
      '/champion-icon/6.png', '/item/1001.png', '/summonerSpell/SummonerFlash.png',
      '/ranked-emblem/emblem-gold.png', '/tft-regalia/TFT_Regalia_Gold.png']) {
      const response = await fetch(origin + path);
      assert.equal(response.status, 200, `Missing development image: ${path}`);
      assert.match(response.headers.get('content-type'), /^image\/png/);
      await response.arrayBuffer();
    }
    const page = await fetch(origin + '/');
    assert.equal(page.status, 200);
    assert.match(await page.text(), /\/src\/main.jsx/);
    console.log('PASS: frontend entry and all image categories are served without image-module imports.');
  }
} finally {
  await server.close();
}
