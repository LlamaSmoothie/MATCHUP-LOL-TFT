import test from 'node:test';
import assert from 'node:assert/strict';
import { createMatchDetails, detailRequest } from '../../frontend/src/matchDetails.js';

const request = { game: 'lol', region: 'North America', name: 'Source#A', matchId: 'NA1_1' };
const result = { game: 'lol', matchId: 'NA1_1', match: { context: {}, combat: {}, economy: {}, vision: {}, objectives: {}, sustain: {} },
  participants: [{ index: 0, name: 'Other#B', canSearch: true }, { index: 1, name: 'Unknown', canSearch: false }] };
const target = { game: 'lol', region: 'North America', name: 'Current#NEW' };
const response = (body, ok = true) => ({ ok, json: async () => body });
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; };

test('opening details reads just one match without initiating AI or profile requests', async () => {
  const calls = [];
  const store = createMatchDetails(async (url) => { calls.push(new URL(url, 'http://local')); return response(result); });
  assert.equal(calls.length, 0);
  await store.load(request);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].pathname, '/api/match');
  assert.deepEqual(Object.fromEntries(calls[0].searchParams), request);
  assert.deepEqual(store.getSnapshot().data, result);
});

test('participant navigation uses submitted identity and region and resolves the current Riot ID', async () => {
  const calls = [];
  const original = { ...request };
  const store = createMatchDetails(async (url) => { calls.push(new URL(url, 'http://local')); return response(calls.length === 1 ? result : target); });
  await store.load(original);
  original.name = 'EditedForm#A';
  original.region = 'Korea';
  assert.deepEqual(await store.profile(0), target);
  assert.equal(calls[1].pathname, '/api/match-player');
  assert.deepEqual(Object.fromEntries(calls[1].searchParams), { ...request, participant: '0' });
  assert.equal(await store.profile(1), null);
  assert.equal(await store.profile(999), null);
  assert.equal(calls.length, 2);
});

test('changing the selected match rejects late detail responses', async () => {
  const old = deferred();
  let oldSignal;
  const store = createMatchDetails((url, options) => {
    if (url.includes('NA1_1')) { oldSignal = options.signal; return old.promise; }
    return Promise.resolve(response({ ...result, matchId: 'NA1_2' }));
  });
  const pending = store.load(request);
  await store.load({ ...request, matchId: 'NA1_2' });
  assert.equal(oldSignal.aborted, true);
  old.resolve(response(result));
  await pending;
  assert.equal(store.getSnapshot().data.matchId, 'NA1_2');
});

test('back or a new match cancels profile resolution without navigating to a stale player', async () => {
  for (const close of ['cancel', 'load']) {
    const pending = deferred();
    let signal;
    const store = createMatchDetails((url, options) => {
      if (url.startsWith('/api/match-player')) { signal = options.signal; return pending.promise; }
      return Promise.resolve(response(result));
    });
    await store.load(request);
    const navigation = store.profile(0);
    if (close === 'cancel') store.cancel();
    else await store.load(request);
    assert.equal(signal.aborted, true);
    pending.resolve(response(target));
    assert.equal(await navigation, null);
  }
});

test('double clicks resolve a participant once and errors preserve free statistics for retry', async () => {
  const pending = deferred();
  let profiles = 0;
  const store = createMatchDetails((url) => {
    if (!url.startsWith('/api/match-player')) return Promise.resolve(response(result));
    profiles += 1;
    return profiles === 1 ? pending.promise : Promise.resolve(response(target));
  });
  await store.load(request);
  const first = store.profile(0);
  assert.equal(await store.profile(0), null);
  pending.resolve(response({ error: 'Limited.', retryAfter: 7 }, false));
  assert.equal(await first, null);
  assert.equal(profiles, 1);
  assert.match(store.getSnapshot().profileError, /Retry in 7 seconds/);
  assert.deepEqual(store.getSnapshot().data, result);
  assert.deepEqual(await store.profile(0), target);
});

test('failed details can retry and mismatched responses cannot replace the selected match', async () => {
  for (const bad of [null, {}, { ...result, matchId: 'WRONG' }, { ...result, participants: [{}] }]) {
    let calls = 0;
    const store = createMatchDetails(async () => response(++calls === 1 ? bad : result));
    await store.load(request);
    assert.equal(store.getSnapshot().data, null);
    assert.match(store.getSnapshot().error, /invalid match details/);
    await store.load(request);
    assert.deepEqual(store.getSnapshot().data, result);
  }
});

test('detail requests contain only submitted identity and selected match ID', () => {
  assert.deepEqual(detailRequest({ ...request, filters: { queue: 420 } }, { id: request.matchId, items: [1] }), request);
});
