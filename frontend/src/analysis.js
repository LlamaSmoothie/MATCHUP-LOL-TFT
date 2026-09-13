// No request is made until the player explicitly asks for analysis.
export function createAnalysis(fetcher = (...args) => fetch(...args)) {
  const empty = () => ({ data: null, error: '', loading: false });
  let state = empty();
  let generation = 0;
  let controller;
  const listeners = new Set();
  const publish = (changes) => {
    state = { ...state, ...changes };
    listeners.forEach((listener) => listener());
  };
  return {
    getSnapshot: () => state,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    async run(payload) {
      if (state.loading || state.data) return;
      controller = new AbortController();
      const request = ++generation;
      publish({ loading: true, error: '' });
      try {
        const response = await fetcher('/api/analyze', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload), signal: controller.signal,
        });
        const result = await response.json();
        if (request !== generation) return;
        if (!response.ok) {
          throw new Error((result.error || 'Analysis failed.')
            + (result.retryAfter ? ` Retry in ${result.retryAfter} seconds.` : ''));
        }
        if (!result.analysis || typeof result.analysis.summary !== 'string'
          || ['observations', 'reviewSuggestions', 'limitations'].some((key) => !Array.isArray(result.analysis[key])
            || result.analysis[key].some((value) => typeof value !== 'string'))
          || result.matchId !== payload.matchId || !result.match || typeof result.match !== 'object'
          || ['context', 'combat', 'economy', 'vision', 'objectives', 'sustain'].some((key) =>
            !result.match[key] || typeof result.match[key] !== 'object' || Array.isArray(result.match[key]))
          || !Number.isFinite(result.generatedAt)) throw new Error('The server returned an invalid analysis.');
        publish({ data: result, loading: false });
      } catch (error) {
        if (request !== generation) return;
        publish({ loading: false, error: error.name === 'AbortError' ? '' : error.message });
      }
    },
    reset() { generation += 1; controller?.abort(); publish(empty()); },
    cancel() { generation += 1; controller?.abort(); },
  };
}

export function analysisRequest(identity, match) {
  return { game: identity.game, region: identity.region, name: identity.name,
    matchId: match.id };
}
