import assert from 'node:assert/strict';
import test from 'node:test';
import { createLiveProfiles } from '../../frontend/src/liveProfiles.js';

const request = { game: 'lol', region: 'North America', name: 'Source#A', gameId: '123' };
const players = Array.from({ length: 4 }, (_, index) => ({ index, name: `Player${index}#A`, canLoadProfile: true }));
const result = (player, context = request) => ({ ...context, participant: player.index, playerName: player.name,
  rank: { status: 'ready', queues: [{ queue: 'Solo/Duo', status: 'unranked' }] },
  history: { status: 'ready', sampleSize: 1, sampleLimit: 20, requestedMatches: 1,
    mostPlayed: { champion: '6', games: 1 }, averageKills: 6, averageDeaths: 2, averageAssists: 4, kda: 5, deathless: false } });
const reply = (data, status = 200) => ({ ok: status === 200, status, json: async () => data });
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r; }); return { resolve, promise }; };
const flush = () => new Promise((resolve) => setImmediate(resolve));

test('profiles wait for activation, skip unidentified players, and load two at a time progressively', async () => {
  const calls = [], pending = [];
  const store = createLiveProfiles(async (url) => {
    calls.push(url); const wait = deferred(); pending.push(wait); return wait.promise;
  });
  assert.equal(calls.length, 0);
  const loading = store.load(request, [...players, { index: 8, name: 'Bot', canLoadProfile: false }]);
  assert.equal(calls.length, 2);
  pending[0].resolve(reply(result(players[0]))); await flush();
  assert.equal(calls.length, 3);
  assert.equal(store.getSnapshot().rows[0].data.history.kda, 5);
  assert.equal(store.getSnapshot().loading, true);
  pending[1].resolve(reply(result(players[1]))); await flush();
  assert.equal(calls.length, 4);
  pending[2].resolve(reply(result(players[2]))); pending[3].resolve(reply(result(players[3])));
  await loading;
  assert.equal(store.getSnapshot().loading, false);
  assert.equal(Object.keys(store.getSnapshot().rows).length, 4);
  const params = new URL(calls[0], 'http://localhost').searchParams;
  assert.equal(params.get('name'), request.name); assert.equal(params.get('participant'), '0');
  assert.equal(params.get('gameId'), '123'); assert.equal(params.has('puuid'), false);
});

test('hiding or leaving cancels pending requests, ignores late results, and prevents queued lookups', async () => {
  const waiting = deferred(); const signals = [];
  const store = createLiveProfiles(async (_, options) => { signals.push(options.signal); return waiting.promise; });
  const loading = store.load(request, players);
  store.cancel();
  assert.ok(signals.every((s) => s.aborted));
  waiting.resolve(reply(result(players[0]))); await loading;
  assert.equal(signals.length, 2);
  assert.deepEqual(store.getSnapshot().rows, {});
});

test('new player or game rejects late historical results', async () => {
  const waiting = deferred(); let calls = 0;
  const next = { ...request, gameId: '456', name: 'Next#A' };
  const store = createLiveProfiles(async () => ++calls === 1 ? waiting.promise : reply(result(players[1], next)));
  const previous = store.load(request, [players[0]]);
  await store.load(next, [players[1]]);
  waiting.resolve(reply(result(players[0]))); await previous;
  assert.equal(store.getSnapshot().rows[1].data.gameId, '456');
  assert.equal(store.getSnapshot().rows[0], undefined);
});

test('rate limits stop the queue, preserve completed rank data, and allow manual retry', async () => {
  let calls = 0;
  const store = createLiveProfiles(async (url) => {
    calls += 1;
    const index = Number(new URL(url, 'http://localhost').searchParams.get('participant'));
    return reply({ ...result(players[index]), history: { status: 'unavailable', message: 'Limited' }, retryAfter: 12 });
  });
  await store.load(request, players);
  assert.equal(calls, 2);
  assert.match(store.getSnapshot().error, /12 seconds/);
  assert.equal(store.getSnapshot().rows[0].data.rank.status, 'ready');
  await store.load(request, [players[2]]);
  assert.equal(calls, 3);
});

test('expired game stops new lookups; ordinary errors only affect that player', async () => {
  let calls = 0;
  const store = createLiveProfiles(async () => { calls += 1; return reply({ error: 'Game changed' }, 409); });
  await store.load(request, players);
  assert.equal(calls, 2); assert.match(store.getSnapshot().error, /Game changed/);
  const partial = createLiveProfiles(async (url) => {
    const index = Number(new URL(url, 'http://localhost').searchParams.get('participant'));
    return index === 0 ? reply({ error: 'Unavailable' }, 502) : reply(result(players[index]));
  });
  await partial.load(request, players);
  assert.equal(partial.getSnapshot().rows[0].error, 'Unavailable');
  assert.equal(partial.getSnapshot().rows[3].data.playerName, players[3].name);
});

test('mismatched and malformed profile statistics are rejected', async () => {
  for (const data of [null, { ...result(players[0]), playerName: 'Wrong#A' },
    { ...result(players[0]), history: { status: 'ready', mostPlayed: {} } },
    { ...result(players[0]), rank: { status: 'unavailable', message: {} } }]) {
    const store = createLiveProfiles(async () => reply(data));
    await store.load(request, [players[0]]);
    assert.match(store.getSnapshot().rows[0].error, /invalid/);
  }
});
