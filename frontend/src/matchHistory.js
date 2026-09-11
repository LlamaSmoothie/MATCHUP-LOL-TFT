// Shared request state is independently testable without a browser or Riot key.
export function createMatchHistory(fetcher = (...args) => fetch(...args)) {
  const empty = () => ({ data: null, identity: null, loading: false, error: '' });
  let state = empty();
  let generation = 0;
  let controller;
  const listeners = new Set();
  const publish = (changes) => {
    state = { ...state, ...changes };
    listeners.forEach((listener) => listener());
  };

  async function run(identity, { append = false, refresh = false } = {}) {
    if (append && (state.loading || !state.data?.pagination.hasMore)) return;
    controller?.abort();
    controller = new AbortController();
    const request = ++generation;
    const previous = state.data;
    const params = new URLSearchParams({
      ...identity, start: String(append ? previous.pagination.nextStart : 0), count: '10',
    });
    if (append) params.set('asOf', String(previous.pagination.asOf));
    if (refresh) params.set('refresh', '1');
    publish({ identity, loading: true, error: '', data: append || refresh ? previous : null });
    try {
      const response = await fetcher(`/api/search?${params}`, { signal: controller.signal });
      const payload = await response.json();
      if (request !== generation) return;
      if (!response.ok) {
        const retry = payload.retryAfter ? ` Retry in ${payload.retryAfter} seconds.` : '';
        throw new Error((payload.error || 'Search failed.') + retry);
      }
      const matches = mergeMatches(append ? previous.matches : [], payload.matches);
      publish({ data: { ...payload, matches }, loading: false });
    } catch (error) {
      if (request !== generation) return;
      publish({ error: error.name === 'AbortError' ? '' : error.message, loading: false });
    }
  }

  return {
    getSnapshot: () => state,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    search: (identity) => run({ ...identity, name: identity.name.trim() }),
    loadMore: () => state.identity && run(state.identity, { append: true }),
    refresh: () => !state.loading && state.identity && run(state.identity, { refresh: true }),
    cancel: () => { generation += 1; controller?.abort(); },
    reset: () => {
      generation += 1;
      controller?.abort();
      publish(empty());
    },
  };
}

export function mergeMatches(existing, incoming) {
  return [...new Map([...existing, ...incoming].map((match) => [match.id, match])).values()];
}

export function matchSummary(game, matches) {
  const valid = game === 'lol'
    ? matches.filter((match) => ['Victory', 'Defeat'].includes(match.result))
    : matches.filter((match) => match.placementNumber >= 1 && match.placementNumber <= 8);
  const wins = valid.filter((match) => game === 'lol'
    ? match.result === 'Victory' : match.placementNumber <= 4).length;
  return {
    label: game === 'lol' ? 'Win rate' : 'Top 4 rate',
    count: valid.length,
    percent: valid.length ? Math.round(100 * wins / valid.length) : null,
  };
}

export function formatAge(timestamp, now = Date.now()) {
  if (!timestamp) return 'Unknown';
  const minutes = Math.max(1, Math.floor((now - timestamp) / 60000));
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}
