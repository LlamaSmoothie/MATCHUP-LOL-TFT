import assert from 'node:assert/strict';
import test from 'node:test';
import { createGameData, validLiveGame, validTimeline, formatGameTime } from '../../frontend/src/gameData.js';

const identity = { game: 'lol', region: 'North America', name: 'Source#A' };
const active = { ...identity, active: true, gameId: '1', participants: [], local: { status: 'unavailable' }, pollAfter: 5 };
const inactive = { ...identity, active: false, pollAfter: null };
const reply = (data, ok = true) => ({ ok, json: async () => data });
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r; }); return { resolve, promise }; };
function clock() {
  const jobs = new Map(); let n = 0;
  return { jobs, setTimeout(fn, ms) { jobs.set(++n, { fn, ms }); return n; }, clearTimeout(id) { jobs.delete(id); },
    async tick() { const [id, job] = jobs.entries().next().value; jobs.delete(id); await job.fn(); } };
}

test('inactive players are checked once without polling or extra requests', async () => {
  const timers = clock(); const urls = [];
  const store = createGameData('/api/live-game', validLiveGame, async (url) => { urls.push(url); return reply(inactive); }, timers);
  await store.load(identity);
  assert.equal(urls.length, 1); assert.equal(timers.jobs.size, 0);
  assert.equal(store.getSnapshot().data.active, false);
});

test('only ongoing games poll and tracking stops as soon as a game ends', async () => {
  const timers = clock(); const responses = [active, active, inactive];
  const store = createGameData('/api/live-game', validLiveGame, async () => reply(responses.shift()), timers);
  await store.load(identity);
  assert.equal([...timers.jobs.values()][0].ms, 5000);
  await timers.tick(); assert.equal(timers.jobs.size, 1);
  await timers.tick(); assert.equal(timers.jobs.size, 0); assert.equal(store.getSnapshot().data.active, false);
});

test('leaving the profile or hiding the page cancels polling and pending responses', async () => {
  const timers = clock(); const pending = deferred(); let signal;
  const store = createGameData('/api/live-game', validLiveGame, async (_, opts) => { signal = opts.signal; return pending.promise; }, timers);
  const loading = store.load(identity); store.cancel();
  assert.equal(signal.aborted, true);
  pending.resolve(reply(active)); await loading;
  assert.equal(store.getSnapshot().data, null); assert.equal(timers.jobs.size, 0);
});

test('player changes reject old results and use the submitted identity', async () => {
  const pending = deferred(); const timers = clock(); let count = 0;
  const next = { ...identity, name: 'Next#A' };
  const store = createGameData('/api/live-game', validLiveGame, async () => ++count === 1 ? pending.promise : reply({ ...inactive, ...next }), timers);
  const old = store.load(identity); await store.load(next);
  pending.resolve(reply(active)); await old;
  assert.equal(store.getSnapshot().data.name, 'Next#A'); assert.equal(timers.jobs.size, 0);
});

test('errors and malformed live data clear old statistics and stop automatic requests', async () => {
  const timers = clock(); const replies = [reply(active), reply({ error: 'Limited', retryAfter: 30 }, false), reply(null)];
  const store = createGameData('/api/live-game', validLiveGame, async () => replies.shift(), timers);
  await store.load(identity); await timers.tick();
  assert.equal(store.getSnapshot().data, null); assert.match(store.getSnapshot().error, /30 seconds/); assert.equal(timers.jobs.size, 0);
  await store.load(identity); assert.match(store.getSnapshot().error, /invalid/);
});

test('completed timelines load independently without polling or generating AI', async () => {
  const timers = clock(); const urls = []; const request = { ...identity, matchId: 'NA1_1' };
  const data = { game: 'lol', matchId: request.matchId, available: true, participants: [], samples: [{ timestamp: 60001 }], events: [] };
  const store = createGameData('/api/match-timeline', validTimeline, async (url) => { urls.push(url); return reply(data); }, timers);
  await store.load(request);
  assert.equal(urls.length, 1); assert.ok(urls[0].startsWith('/api/match-timeline?'));
  assert.equal(timers.jobs.size, 0); assert.equal(store.getSnapshot().data, data);
  assert.equal(validTimeline({ ...data, matchId: 'OTHER' }, request), false);
  assert.equal(validTimeline({ ...data, samples: [null] }, request), false);
});

test('failed timeline requests support retry and out-of-order results are ignored', async () => {
  const timers = clock(); const pending = deferred(); let n = 0;
  const request = { ...identity, matchId: 'NA1_2' };
  const data = { game: 'lol', matchId: request.matchId, available: false, samples: [], events: [] };
  const store = createGameData('/api/match-timeline', validTimeline, async () => ++n === 1 ? pending.promise : reply(data), timers);
  const old = store.load({ ...identity, matchId: 'NA1_1' }); await store.load(request);
  pending.resolve(reply({ error: 'Old error' }, false)); await old;
  assert.equal(store.getSnapshot().data.matchId, 'NA1_2'); assert.equal(store.getSnapshot().error, '');
});

test('timeline times use actual milliseconds and preserve unavailable values', () => {
  assert.equal(formatGameTime(61555), '1:01'); assert.equal(formatGameTime(0), '0:00');
  assert.equal(formatGameTime(null), '—'); assert.equal(formatGameTime(-1), '—');
});
