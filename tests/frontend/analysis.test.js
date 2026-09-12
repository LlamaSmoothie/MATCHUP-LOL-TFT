import test from 'node:test';
import assert from 'node:assert/strict';
import { analysisRequest, createAnalysis } from '../../frontend/src/analysis.js';

const payload = { game: 'lol', region: 'North America', name: 'Player#A',
  matchIds: ['NA1_1'], filters: { queue: '', role: '', patch: '' } };
const result = { analysis: { summary: 'One game.', observations: ['One win.'],
  reviewSuggestions: ['What happened before your death?'], limitations: ['Small sample.'] },
  sample: { sampleSize: 1, championCount: 1, coveredChampionCount: 1 }, generatedAt: 1000 };
const response = (body = result, ok = true) => ({ ok, json: async () => body });
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; };

test('analysis only runs on demand, posts identifiers/filters, and ignores double clicks', async () => {
  const wait = deferred();
  const calls = [];
  const store = createAnalysis((...args) => { calls.push(args); return wait.promise; });
  assert.equal(calls.length, 0);
  const pending = store.run(payload);
  await store.run(payload);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], '/api/analyze');
  assert.equal(calls[0][1].method, 'POST');
  assert.equal(calls[0][1].headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(calls[0][1].body), payload);
  assert.equal(store.getSnapshot().loading, true);
  wait.resolve(response());
  await pending;
  assert.deepEqual(store.getSnapshot(), { loading: false, error: '', data: result });
  await store.run(payload);
  assert.equal(calls.length, 1);
});

test('errors stay separate from match history and can be retried', async () => {
  let calls = 0;
  const store = createAnalysis(async () => ++calls === 1
    ? response({ error: 'Rate limited.', retryAfter: 10 }, false) : response());
  await store.run(payload);
  assert.equal(store.getSnapshot().data, null);
  assert.match(store.getSnapshot().error, /Retry in 10 seconds/);
  await store.run(payload);
  assert.equal(store.getSnapshot().error, '');
  assert.deepEqual(store.getSnapshot().data, result);
});

test('changing sample or unmounting aborts and ignores a late AI response', async () => {
  for (const action of ['reset', 'cancel']) {
    const wait = deferred();
    let signal;
    const store = createAnalysis((url, options) => { signal = options.signal; return wait.promise; });
    const pending = store.run(payload);
    store[action]();
    assert.equal(signal.aborted, true);
    wait.resolve(response());
    await pending;
    assert.equal(store.getSnapshot().data, null);
    if (action === 'reset') assert.equal(store.getSnapshot().loading, false);
  }
});

test('each player, page and filter selection gets a distinct request context', () => {
  const identity = { game: 'lol', region: 'North America', name: 'Player#A' };
  const filters = { queue: '', role: '', patch: '' };
  const first = analysisRequest(identity, [{ id: 'b', kills: 999, teamA: ['private'] }, { id: 'a' }, { id: 'a' }], filters);
  assert.deepEqual(first.matchIds, ['a', 'b']);
  assert.equal(Object.hasOwn(first, 'kills'), false);
  assert.equal(Object.hasOwn(first, 'teamA'), false);
  assert.notDeepEqual(first, analysisRequest({ ...identity, name: 'Other#B' }, [{ id: 'a' }], filters));
  assert.notDeepEqual(first, analysisRequest(identity, [{ id: 'a' }, { id: 'b' }, { id: 'c' }], filters));
  assert.notDeepEqual(first, analysisRequest(identity, [{ id: 'a' }, { id: 'b' }], { ...filters, queue: '420' }));
  filters.queue = '450';
  assert.equal(first.filters.queue, '');
});

test('malformed provider payloads cannot crash the analysis panel', async () => {
  for (const body of [{}, { ...result, analysis: { ...result.analysis, observations: [{}] } }]) {
    const store = createAnalysis(async () => response(body));
    await store.run(payload);
    assert.equal(store.getSnapshot().data, null);
    assert.match(store.getSnapshot().error, /invalid analysis/);
  }
});
