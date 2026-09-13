// Detail reads and participant resolution never generate AI requests.
export function detailRequest(identity, match) {
  return { game: identity.game, region: identity.region, name: identity.name, matchId: match.id };
}

export function createMatchDetails(fetcher = (...args) => fetch(...args)) {
  let state = { data: null, loading: false, error: '', profileLoading: null, profileError: '' };
  let generation = 0;
  let detailController;
  let profileController;
  let context;
  const listeners = new Set();
  const publish = (changes) => { state = { ...state, ...changes }; listeners.forEach((listener) => listener()); };
  async function get(path, request, signal) {
    const response = await fetcher(`${path}?${new URLSearchParams(request)}`, { signal });
    const result = await response.json();
    if (!response.ok) throw new Error((result.error || 'Request failed.')
      + (result.retryAfter ? ` Retry in ${result.retryAfter} seconds.` : ''));
    return result;
  }
  return {
    getSnapshot: () => state,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    async load(request) {
      detailController?.abort();
      profileController?.abort();
      detailController = new AbortController();
      context = { ...request };
      const current = ++generation;
      publish({ data: null, loading: true, error: '', profileLoading: null, profileError: '' });
      try {
        const data = await get('/api/match', context, detailController.signal);
        if (current !== generation) return;
        if (!data || data.game !== context.game || data.matchId !== context.matchId || !data.match?.context
          || !Array.isArray(data.participants) || data.participants.some((p) => !p || !Number.isInteger(p.index)
            || typeof p.name !== 'string' || typeof p.canSearch !== 'boolean')
          || (data.game === 'lol' && ['combat', 'economy', 'vision', 'objectives', 'sustain'].some((key) =>
            !data.match[key] || typeof data.match[key] !== 'object')))
          throw new Error('The server returned invalid match details.');
        publish({ data, loading: false });
      } catch (error) {
        if (current === generation) publish({ loading: false, error: error.name === 'AbortError' ? '' : error.message });
      }
    },
    async profile(participant) {
      if (state.profileLoading !== null || !state.data?.participants.some((p) => p.index === participant && p.canSearch)) return null;
      profileController = new AbortController();
      const current = generation;
      publish({ profileLoading: participant, profileError: '' });
      try {
        const identity = await get('/api/match-player', { ...context, participant }, profileController.signal);
        if (current !== generation) return null;
        if (!identity || identity.game !== context.game || identity.region !== context.region
          || typeof identity.name !== 'string' || !/^[^#]+#[^#]+$/.test(identity.name))
          throw new Error('The server returned an invalid player profile.');
        publish({ profileLoading: null });
        return identity;
      } catch (error) {
        if (current === generation) publish({ profileLoading: null, profileError: error.name === 'AbortError' ? '' : error.message });
        return null;
      }
    },
    cancel() { generation += 1; detailController?.abort(); profileController?.abort(); },
  };
}
