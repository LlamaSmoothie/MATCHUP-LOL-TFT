import test from 'node:test';
import assert from 'node:assert/strict';
import { asset, fallbackImage } from '../../frontend/src/assets.js';

test('image URLs work at the root and under a deployment base path', () => {
  assert.equal(asset('profileicon/6.png'), '/profileicon/6.png');
  assert.equal(asset('champion-icon/6.png', '/tftlol/'), '/tftlol/champion-icon/6.png');
  assert.equal(asset('picture/a b.png', '/tftlol'), '/tftlol/picture/a%20b.png');
});

test('TFT character IDs use the fallback without requesting nonexistent LoL icons', () => {
  assert.equal(asset('champion-icon/TFT13_Vi.png'), '/picture/TFT.png');
  assert.equal(asset('champion-icon/.png', '/app/'), '/app/picture/TFT.png');
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
