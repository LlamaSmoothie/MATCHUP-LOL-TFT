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
    assert.ok(!html.includes('Analyze this match'), 'AI analysis must stay outside champion statistics.');
    const { default: AiAnalysis, AnalysisResult } = await server.ssrLoadModule('/src/AiAnalysis.jsx');
    const request = { game: 'lol', region: 'North America', name: 'Example#NA1',
      matchId: 'fixture' };
    const ai = renderToStaticMarkup(React.createElement(AiAnalysis, { request }));
    assert.ok(ai.includes('Analyze this match'));
    assert.ok(ai.includes('match statistics and team totals are sent to OpenAI'));
    const { LolMatchCard, TftMatchCard } = await server.ssrLoadModule('/src/App.jsx');
    const card = renderToStaticMarkup(React.createElement(LolMatchCard, {
      match: { ...matches[0], spells: [], items: [], teamA: [], teamB: [] },
      now: 1000, onOpen: () => {},
    }));
    assert.ok(card.includes('aria-label="View match details:'), 'Match cards need a keyboard-accessible detail button.');
    assert.ok(!card.includes('Analyze this match'), 'AI controls belong inside match details.');
    const tftCard = renderToStaticMarkup(React.createElement(TftMatchCard, {
      match: { id: 'tft-fixture', placement: '1st', placementNumber: 1, units: [], traits: [] },
      now: 1000, onOpen: () => {},
    }));
    assert.ok(tftCard.includes('aria-label="View match details:'));
    const { MatchDetailContent } = await server.ssrLoadModule('/src/MatchDetail.jsx');
    const evidence = { context: { queue: 'ARAM', patch: '16.18', result: 'Victory', role: 'UNKNOWN' },
      combat: { kills: 0, deaths: 0, assists: 0 }, economy: { csPerMinute: 5.5 }, vision: {}, objectives: {}, sustain: {} };
    const matchDetails = renderToStaticMarkup(React.createElement(MatchDetailContent, {
      data: { game: 'lol', playerName: request.name, match: evidence, participants: [
        { index: 0, name: request.name, isSearchedPlayer: true, canSearch: true, teamId: 100, champion: '6',
          statistics: evidence, items: ['1001'], result: 'Victory', role: 'TOP' },
        { index: 1, name: 'Unavailable player', canSearch: false, teamId: 200, champion: '6', items: [] },
      ] }, request, onProfileSearch: () => {},
    }));
    for (const text of ['Scoreboard', 'Match statistics', 'Current player', 'Search Example#NA1',
      'Analyze this match', 'Boots', '5.5 / min', 'Profile unavailable in this match record', 'disabled=""']) {
      assert.ok(matchDetails.includes(text), `Missing match detail content: ${text}`);
    }
    const tftDetails = renderToStaticMarkup(React.createElement(MatchDetailContent, {
      data: { game: 'tft', participants: [{ index: 0, name: request.name, canSearch: true,
        placement: 1, level: 9, goldLeft: 0, units: [{ champion: 'TFT_Example', name: 'Example unit', stars: 2 }] }] },
      request: { ...request, game: 'tft' }, onProfileSearch: () => {},
    }));
    for (const text of ['TFT placement statistics', 'Search Example#NA1', 'View board', 'Example unit']) {
      assert.ok(tftDetails.includes(text), `Missing TFT detail content: ${text}`);
    }
    assert.ok(!tftDetails.includes('Analyze this match'), 'AI currently supports LoL only.');
    const { TimelineContent } = await server.ssrLoadModule('/src/MatchTimeline.jsx');
    const timeline = renderToStaticMarkup(React.createElement(TimelineContent, { data: {
      frameInterval: 60000, playerId: 1, opponentId: 2,
      participants: [{ id: 1, name: 'Source#A' }, { id: 2, name: 'Other#B' }],
      samples: [{ timestamp: 0, gold: 500, opponentGold: 500, teamGold: 500, opposingTeamGold: 500 },
        { timestamp: 60001, gold: 900, opponentGold: 700, teamGold: 900, opposingTeamGold: 700 }],
      events: [{ timestamp: 50001, type: 'ITEM_PURCHASED', actorId: 1, itemId: 1001, involvement: 'participant' }],
    } }));
    for (const text of ['Gold progression', 'Timeline sample', 'Recorded events', 'Purchased Boots', '0:50', 'Other#B']) {
      assert.ok(timeline.includes(text), `Missing timeline content: ${text}`);
    }
    assert.ok(!timeline.includes('NaN'));
    const { LiveGameContent } = await server.ssrLoadModule('/src/LiveGame.jsx');
    const live = renderToStaticMarkup(React.createElement(LiveGameContent, { data: {
      active: true, game: 'lol', queue: 'Ranked Solo', checkedAt: 1000, pollAfter: 5,
      local: { status: 'connected', gameTime: 62.5, players: [{ name: 'Source#A', championName: 'Urgot',
        team: 'ORDER', kills: 0, deaths: 1, assists: 0, cs: 4, vision: 0.5, items: ['1001'] }], events: [] },
    } }));
    for (const text of ['IN GAME', 'Live player statistics', '1:02', '0 / 1 / 0', 'Boots']) assert.ok(live.includes(text));
    const { PlayerHistory } = await server.ssrLoadModule('/src/LiveRoster.jsx');
    const profileData = { rank: { status: 'ready', queues: [
      { queue: 'Solo/Duo', status: 'ranked', tier: 'GOLD', division: 'II', lp: 32 },
      { queue: 'Flex', status: 'unranked' }] }, history: { status: 'ready', sampleSize: 10, requestedMatches: 10,
      mostPlayed: { champion: '6', games: 4 }, averageKills: 6, averageDeaths: 2, averageAssists: 4, kda: 5, deathless: false } };
    const playerHistory = renderToStaticMarkup(React.createElement(PlayerHistory, { row: { data: profileData } }));
    for (const text of ['Gold II · 32 LP', 'Solo/Duo', 'Flex', 'Unranked', 'Urgot', '4 / 10 games',
      '6.0 / 2.0 / 4.0', '5.00 KDA ratio', '10 eligible of 10']) assert.ok(playerHistory.includes(text), `Missing live profile content: ${text}`);
    const deathless = renderToStaticMarkup(React.createElement(PlayerHistory, { row: { data: {
      ...profileData, history: { ...profileData.history, deathless: true, kda: null } } } }));
    assert.ok(deathless.includes('Deathless sample')); assert.ok(!deathless.includes('Infinity'));
    const publicGame = renderToStaticMarkup(React.createElement(LiveGameContent, { data: {
      active: true, game: 'lol', gameId: '123', queue: 'ARAM', checkedAt: 1000, pollAfter: 5,
      participants: [{ index: 0, name: 'Example#NA1', champion: '6', canLoadProfile: true }],
      local: { status: 'unavailable', message: 'Local feed unavailable.' },
    } }));
    for (const text of ['Player profiles', 'Example#NA1', 'Urgot', 'including ARAM', 'Local feed unavailable.']) assert.ok(publicGame.includes(text));
    console.log('PASS: ongoing roster profiles show ranks, recent champion use, average KDA, and sample labels without a local feed.');
    const idle = renderToStaticMarkup(React.createElement(LiveGameContent, { data: { active: false, message: 'No ongoing game.' } }));
    assert.ok(idle.includes('Automatic tracking is stopped'));
    assert.ok(!idle.includes('Live player statistics'));
    console.log('PASS: timeline charts, event history, active live details, and stopped tracking render.');
    const analysis = { summary: '<script>untrusted</script>', observations: ['One game.'],
      reviewSuggestions: ['Review a replay.'], limitations: ['Small sample.'] };
    const insight = renderToStaticMarkup(React.createElement(AnalysisResult, {
      data: { analysis, matchId: 'fixture', match: { context: { queue: 'ARAM', patch: '16.18', result: 'Victory', role: 'UNKNOWN' },
        combat: { kills: 0, deaths: 0, assists: 0 }, economy: { csPerMinute: 5.5 }, vision: {}, objectives: {}, sustain: {} }, generatedAt: 1000 },
    }));
    assert.ok(insight.includes('&lt;script&gt;untrusted&lt;/script&gt;'));
    assert.ok(!insight.includes('<script>'));
    assert.ok(insight.includes('Questions for this replay'));
    assert.ok(!insight.includes('View match data used'));
    assert.ok(!insight.includes('match-statistics'), 'AI results must not duplicate the match statistics panel.');
    assert.ok(matchDetails.includes('Unavailable'));
    assert.ok(matchDetails.includes('5.5'));
    assert.ok(matchDetails.includes('0 / 0 / 0'));
    console.log('PASS: AI belongs to individual matches, avoids duplicate statistics, and escapes model output.');
    console.log('PASS: match cards open details, with free scoreboards and participant profile controls for both games.');
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
