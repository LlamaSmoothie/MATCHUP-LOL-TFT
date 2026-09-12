import test from 'node:test';
import assert from 'node:assert/strict';
import { championFilterOptions, championStatistics } from '../../frontend/src/championStats.js';
import { createMatchHistory } from '../../frontend/src/matchHistory.js';

const runes = { primary: { style: 8000, perks: [8005, 9101, 9104, 8014] },
  secondary: { style: 8400, perks: [8444, 8451] } };
const match = (id, fields = {}) => ({ id, champion: '6', result: 'Victory',
  kills: 10, deaths: 2, assists: 4, queueId: 420, queue: 'Ranked Solo', role: 'TOP',
  patch: '16.18', finalItems: ['1001', '3071'], runes, ...fields });

test('player champion totals, average combat and weighted KDA use unique matches', () => {
  const one = match('a');
  const result = championStatistics([one, match('b', { result: 'Defeat', kills: 2, deaths: 6, assists: 0 }),
    match('c', { champion: '266' }), one]);
  assert.equal(result.sampleSize, 3);
  const row = result.rows[0];
  assert.equal(row.name, 'Urgot');
  assert.deepEqual([row.games, row.wins, row.losses, row.winRate], [2, 1, 1, 50]);
  assert.equal(row.pickShare, 2 / 3 * 100);
  assert.deepEqual(row.averages, [6, 4, 2]);
  assert.equal(row.kdaRatio, 2); // (10 + 4 + 2 + 0) / (2 + 6), not average match ratios.
});

test('queue, role and patch filters use the filtered player sample as denominator', () => {
  const matches = [match('a'), match('b', { champion: '266' }),
    match('c', { queueId: 450, queue: 'ARAM', role: 'UNKNOWN' }),
    match('d', { role: 'JUNGLE' }), match('e', { patch: '16.17' })];
  assert.equal(championStatistics(matches, { queue: '420' }).sampleSize, 4);
  assert.equal(championStatistics(matches, { role: 'TOP' }).sampleSize, 3);
  assert.equal(championStatistics(matches, { patch: '16.18' }).sampleSize, 4);
  const result = championStatistics(matches, { queue: '420', role: 'TOP', patch: '16.18' });
  assert.equal(result.eligibleCount, 5);
  assert.equal(result.sampleSize, 2);
  assert.equal(result.rows[0].pickShare, 50);
  assert.deepEqual(championFilterOptions(matches).queue, [['450', 'ARAM'], ['420', 'Ranked Solo']]);
  assert.deepEqual(championFilterOptions(matches).patch, [['16.18', '16.18'], ['16.17', '16.17']]);
  assert.equal(championStatistics(matches, { queue: '999' }).rows.length, 0);
});

test('missing data is not zero, and empty or deathless samples stay finite', () => {
  const result = championStatistics([match('a', { kills: null, deaths: null, assists: null,
    finalItems: null, runes: null }), match('b', { kills: 0, deaths: 0, assists: 0, finalItems: [] })]);
  const row = result.rows[0];
  assert.equal(row.games, 2);
  assert.equal(row.combatGames, 1);
  assert.deepEqual(row.averages, [0, 0, 0]);
  assert.equal(row.kdaRatio, null);
  assert.equal(row.deathless, true);
  assert.equal(row.itemGames, 1);
  assert.equal(row.runeGames, 1);
  assert.equal(championStatistics([match('old', { kills: undefined })]).rows[0].averages, null);
  assert.deepEqual(championStatistics([]), { rows: [], sampleSize: 0, eligibleCount: 0 });
});

test('items count once per inventory and rune combinations retain both trees', () => {
  const reordered = { ...runes, primary: { ...runes.primary, perks: [...runes.primary.perks].reverse() } };
  const different = { ...runes, secondary: { style: 8300, perks: [8304, 8347] } };
  const row = championStatistics([match('a', { finalItems: ['3071', '3071', '0'] }),
    match('b', { runes: reordered }), match('c', { runes: different }),
    match('d', { finalItems: null, runes: { primary: runes.primary } })]).rows[0];
  assert.equal(row.itemGames, 3);
  assert.deepEqual(row.items, [{ id: '3071', games: 3 }, { id: '1001', games: 2 }]);
  assert.equal(row.runeGames, 3);
  assert.equal(row.runes.length, 2);
  assert.equal(row.runes[0].games, 2);
});

test('invalid champions and outcomes are excluded and newer duplicate records win', () => {
  const result = championStatistics([match('a'), match('b', { champion: '' }),
    match('c', { result: 'Unknown' }), match('d', { champion: '0' }),
    match('a', { result: 'Defeat' })]);
  assert.equal(result.sampleSize, 1);
  assert.equal(result.rows[0].wins, 0);
});

test('statistics follow pagination, failed loads, refresh and player changes without new requests', async () => {
  let calls = 0;
  const history = createMatchHistory(async () => {
    calls++;
    if (calls === 2) throw new Error('Offline');
    const matches = calls === 1 ? [match('a')] : calls === 3 ? [match('a'), match('b')]
      : [match('new', { champion: '266' })];
    return { ok: true, json: async () => ({ profile: { name: calls === 5 ? 'Other#B' : 'Player#A' },
      matches, pagination: { nextStart: 1, hasMore: true, asOf: 123 } }) };
  });
  const stats = () => championStatistics(history.getSnapshot().data?.matches || []);
  const identity = { game: 'lol', region: 'North America', name: 'Player#A' };
  await history.search(identity);
  assert.equal(stats().sampleSize, 1);
  await history.loadMore();
  assert.equal(stats().sampleSize, 1);
  await history.loadMore();
  assert.equal(stats().sampleSize, 2);
  await history.refresh();
  assert.deepEqual(stats().rows.map((r) => [r.id, r.games]), [['266', 1]]);
  const pending = history.search({ ...identity, name: 'Other#B' });
  assert.equal(stats().sampleSize, 0);
  await pending;
  assert.equal(stats().sampleSize, 1);
  history.reset();
  assert.equal(stats().sampleSize, 0);
  assert.equal(calls, 5);
});
