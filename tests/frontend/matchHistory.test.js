import test from 'node:test';
import assert from 'node:assert/strict';
import { createMatchHistory, formatAge, matchSummary } from '../../frontend/src/matchHistory.js';

const identity = { game: 'lol', region: 'North America', name: 'Player#A' };
const response = (matches, nextStart = null, asOf = 123) => ({
  ok: true, json: async () => ({
    profile: { name: 'Player#A' }, matches,
    pagination: { nextStart, hasMore: nextStart !== null, asOf },
  }),
});
const deferred = () => {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
};

test('load more uses the submitted identity and anchor, deduplicates, and stops', async () => {
  const calls = [];
  const input = { ...identity };
  const history = createMatchHistory(async (url) => {
    calls.push(new URL(url, 'http://localhost'));
    return calls.length === 1
      ? response([{ id: 'a' }, { id: 'b' }], 2)
      : response([{ id: 'b' }, { id: 'c' }]);
  });
  await history.search(input);
  input.name = 'Different#B';
  input.region = 'Korea';
  await history.loadMore();
  assert.equal(calls[1].searchParams.get('name'), identity.name);
  assert.equal(calls[1].searchParams.get('region'), identity.region);
  assert.equal(calls[1].searchParams.get('start'), '2');
  assert.equal(calls[1].searchParams.get('asOf'), '123');
  assert.deepEqual(history.getSnapshot().data.matches.map((m) => m.id), ['a', 'b', 'c']);
  await history.loadMore();
  assert.equal(calls.length, 2);
});

test('an old response cannot replace a new search even if it ignores cancellation', async () => {
  const old = deferred();
  let oldSignal;
  const history = createMatchHistory((url, options) => {
    if (url.includes('Player')) { oldSignal = options.signal; return old.promise; }
    return Promise.resolve(response([{ id: 'new' }]));
  });
  const pending = history.search(identity);
  await history.search({ ...identity, name: 'Other#B' });
  assert.equal(oldSignal.aborted, true);
  old.resolve(response([{ id: 'old' }]));
  await pending;
  assert.equal(history.getSnapshot().data.matches[0].id, 'new');
});

test('switching games clears data and rejects an in-flight response', async () => {
  const upstream = deferred();
  const history = createMatchHistory(() => upstream.promise);
  const pending = history.search(identity);
  history.reset();
  upstream.resolve(response([{ id: 'old' }]));
  await pending;
  assert.deepEqual(history.getSnapshot(), { identity: null, data: null, loading: false, error: '' });
});

test('failed later pages keep loaded results and retry the same offset', async () => {
  let calls = 0;
  const offsets = [];
  const history = createMatchHistory(async (url) => {
    offsets.push(new URL(url, 'http://localhost').searchParams.get('start'));
    calls += 1;
    if (calls === 1) return response([{ id: 'a' }], 1);
    if (calls === 2) return { ok: false, json: async () => ({ error: 'Limited', retryAfter: 5 }) };
    return response([{ id: 'b' }]);
  });
  await history.search(identity);
  await history.loadMore();
  assert.deepEqual(history.getSnapshot().data.matches, [{ id: 'a' }]);
  assert.match(history.getSnapshot().error, /Retry in 5 seconds/);
  await history.loadMore();
  assert.deepEqual(offsets, ['0', '1', '1']);
  assert.deepEqual(history.getSnapshot().data.matches, [{ id: 'a' }, { id: 'b' }]);
});

test('double-clicking load more sends only one page request', async () => {
  const pending = deferred();
  let calls = 0;
  const history = createMatchHistory(async () => ++calls === 1
    ? response([{ id: 'a' }], 1) : pending.promise);
  await history.search(identity);
  const next = history.loadMore();
  await history.loadMore();
  assert.equal(calls, 2);
  pending.resolve(response([{ id: 'b' }]));
  await next;
});

test('refresh starts a new first page and replaces loaded history', async () => {
  const urls = [];
  const history = createMatchHistory(async (url) => {
    urls.push(new URL(url, 'http://localhost'));
    return urls.length === 1 ? response([{ id: 'old' }], 1) : response([{ id: 'new' }], null, 456);
  });
  await history.search(identity);
  await history.refresh();
  assert.equal(urls[1].searchParams.get('refresh'), '1');
  assert.equal(urls[1].searchParams.get('start'), '0');
  assert.equal(urls[1].searchParams.has('asOf'), false);
  assert.deepEqual(history.getSnapshot().data.matches, [{ id: 'new' }]);
});

test('summary uses all loaded results and TFT placements', () => {
  assert.deepEqual(matchSummary('lol', [{ result: 'Victory' }, { result: 'Defeat' },
    { result: 'Victory' }]), { label: 'Win rate', count: 3, percent: 67 });
  assert.deepEqual(matchSummary('tft', [{ placementNumber: 1 }, { placementNumber: 4 },
    { placementNumber: 8 }]), { label: 'Top 4 rate', count: 3, percent: 67 });
  assert.equal(matchSummary('lol', []).percent, null);
});

test('relative ages advance from timestamps without a new network request', () => {
  assert.equal(formatAge(1000, 121000), '2 minutes ago');
  assert.equal(formatAge(1000, 3601000), '1 hour ago');
  assert.equal(formatAge(null), 'Unknown');
});
