// Completed timelines and live polling have independent request lifecycles.
export function createGameData(path, validate, fetcher = (...args) => fetch(...args), timers = globalThis) {
  let state = { data: null, loading: false, error: '' };
  let generation = 0;
  let controller;
  let timer;
  let context;
  const listeners = new Set();
  const publish = (value) => { state = { ...state, ...value }; listeners.forEach((fn) => fn()); };
  function cancel() { generation += 1; controller?.abort(); timers.clearTimeout(timer); }
  async function load(request) {
    cancel();
    context = { ...request };
    const current = generation;
    publish({ data: null, loading: true, error: '' });
    async function poll() {
      if (current !== generation) return;
      controller = new AbortController();
      try {
        const response = await fetcher(`${path}?${new URLSearchParams(context)}`, { signal: controller.signal });
        const data = await response.json();
        if (current !== generation) return;
        if (!response.ok) throw new Error((data?.error || 'Request failed.')
          + (data?.retryAfter ? ` Retry in ${data.retryAfter} seconds.` : ''));
        if (!validate(data, context)) throw new Error('The server returned invalid game data.');
        publish({ data, loading: false, error: '' });
        if (path === '/api/live-game' && data.active && Number.isFinite(data.pollAfter) && data.pollAfter > 0)
          timer = timers.setTimeout(poll, Math.max(5000, data.pollAfter * 1000));
      } catch (error) {
        if (current === generation) publish({ data: null, loading: false, error: error.name === 'AbortError' ? '' : error.message });
      }
    }
    await poll();
  }
  return { getSnapshot: () => state, subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn); }, load, cancel };
}

export const validTimeline = (data, request) => Boolean(data && data.game === 'lol' && data.matchId === request.matchId
  && typeof data.available === 'boolean' && Array.isArray(data.samples) && Array.isArray(data.events)
  && (!data.available || (Array.isArray(data.participants) && data.samples.every((s) => s && Number.isFinite(s.timestamp))
    && data.events.every((e) => e && typeof e.type === 'string' && Number.isFinite(e.timestamp)))));

export const validLiveGame = (data, request) => Boolean(data && data.game === request.game && data.region === request.region
  && data.name === request.name && typeof data.active === 'boolean'
  && (!data.active || (typeof data.gameId === 'string' && Array.isArray(data.participants)
    && data.local && typeof data.local.status === 'string'
    && (data.local.status !== 'connected' || (Array.isArray(data.local.players) && Array.isArray(data.local.events))))));

export function formatGameTime(milliseconds) {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return '—';
  const seconds = Math.floor(milliseconds / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}
