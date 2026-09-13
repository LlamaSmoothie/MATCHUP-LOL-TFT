// Historical roster data loads once per game, independently of live-score polling.
export function createLiveProfiles(fetcher = (...args) => fetch(...args)) {
  let state = { rows: {}, loading: false, error: '' };
  let generation = 0;
  const controllers = new Set();
  const listeners = new Set();
  const publish = (changes) => { state = { ...state, ...changes }; listeners.forEach((fn) => fn()); };
  function cancel() { generation += 1; controllers.forEach((c) => c.abort()); controllers.clear(); }
  async function load(request, participants) {
    cancel();
    const current = generation;
    const context = { ...request };
    const queue = participants.filter((p) => p.canLoadProfile && Number.isInteger(p.index));
    let cursor = 0, stopped = false;
    publish({ rows: {}, loading: queue.length > 0, error: '' });
    async function worker() {
      while (current === generation && !stopped && cursor < queue.length) {
        const player = queue[cursor++];
        const controller = new AbortController();
        controllers.add(controller);
        try {
          const response = await fetcher(`/api/live-player?${new URLSearchParams({ ...context, participant: player.index })}`, { signal: controller.signal });
          const data = await response.json();
          if (current !== generation) return;
          if (response.status === 429 || response.status === 409 || data?.retryAfter) {
            stopped = true;
            publish({ error: data?.retryAfter ? `Riot is rate limiting requests. Retry player stats in ${data.retryAfter} seconds.`
              : data?.error || 'The game status changed. Check ongoing game again.' });
          }
          if (!response.ok) throw new Error(data?.error || 'Could not load player statistics.');
          if (!validLiveProfile(data, context, player)) throw new Error('The server returned invalid player statistics.');
          publish({ rows: { ...state.rows, [player.index]: { data } } });
        } catch (error) {
          if (current === generation) publish({ rows: { ...state.rows, [player.index]: { error: error.message } } });
        } finally { controllers.delete(controller); }
      }
    }
    await Promise.all([worker(), worker()]);
    if (current === generation) publish({ loading: false });
  }
  return { getSnapshot: () => state, subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn); }, load, cancel };
}

function validLiveProfile(data, request, player) {
  const numeric = (n) => n === null || (Number.isFinite(n) && n >= 0);
  if (!data || data.game !== request.game || data.region !== request.region || data.name !== request.name
    || data.gameId !== request.gameId || data.participant !== player.index || data.playerName !== player.name) return false;
  const rank = data.rank, history = data.history;
  if (!rank || !history || !['ready', 'unavailable'].includes(rank.status) || !['ready', 'unavailable'].includes(history.status)) return false;
  if ([rank, history].some((section) => section.message !== undefined && typeof section.message !== 'string')) return false;
  if (rank.status === 'ready' && (!Array.isArray(rank.queues) || rank.queues.some((q) => !q || typeof q.queue !== 'string'
    || !['ranked', 'unranked', 'unavailable'].includes(q.status) || (q.status === 'ranked'
      && (typeof q.tier !== 'string' || !q.tier || typeof q.division !== 'string' || !Number.isFinite(q.lp)))))) return false;
  if (history.status === 'ready' && (!Number.isInteger(history.sampleSize) || history.sampleSize < 0 || history.sampleSize > 20
    || !Number.isInteger(history.requestedMatches) || !Number.isInteger(history.sampleLimit)
    || !['averageKills', 'averageDeaths', 'averageAssists', 'kda'].every((key) => numeric(history[key]))
    || typeof history.deathless !== 'boolean' || (history.mostPlayed !== null && (!history.mostPlayed
      || typeof history.mostPlayed.champion !== 'string' || !Number.isInteger(history.mostPlayed.games))))) return false;
  return true;
}
