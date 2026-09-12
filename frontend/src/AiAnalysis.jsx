import React from 'react';
import { Sparkles } from 'lucide-react';
import { createAnalysis } from './analysis.js';

export default function AiAnalysis({ request, sampleSize, historyLoading = false }) {
  const [store] = React.useState(() => createAnalysis());
  const { data, error, loading } = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const titleId = React.useId();
  React.useEffect(() => () => store.cancel(), [store]);
  const tooMany = request.matchIds.length > 200;
  return <section className="ai-analysis" aria-labelledby={titleId} aria-busy={loading}>
    <div className="stats-heading">
      <h3 id={titleId}><Sparkles size={19} aria-hidden="true" /> AI match insights</h3>
      <button type="button" className="stats-button"
        disabled={loading || historyLoading || !sampleSize || tooMany || Boolean(data)}
        onClick={() => store.run(request)}>
        {loading ? 'Analyzing…' : data ? 'Analysis ready' : error ? 'Retry analysis' : 'Analyze my matches'}
      </button>
    </div>
    <p className="stats-note">Analyze {sampleSize} matches using the current filters, with details for up to 10 most-played champions.
      On click, aggregate statistics are sent to OpenAI. Player identifiers are excluded.</p>
    {tooMany && <p className="stats-note">Analysis supports up to 200 loaded matches. Refresh history to start a smaller sample.</p>}
    {loading && <p role="status">Preparing insights. Your match history remains available.</p>}
    {error && <p className="ai-error" role="alert">{error}</p>}
    {data && <AnalysisResult data={data} />}
  </section>;
}

export function AnalysisResult({ data }) {
  const { analysis, sample } = data;
  return <div className="ai-result">
    <p>{analysis.summary}</p>
    <div className="ai-result-columns">
      {[['observations', 'What the sample shows'], ['reviewSuggestions', 'Questions for your next replay'],
        ['limitations', 'Limits of this analysis']].map(([key, title]) => <div key={key}>
        <h4>{title}</h4><ul>{analysis[key].map((text, index) => <li key={index}>{text}</li>)}</ul>
      </div>)}
    </div>
    <p className="stats-note">AI-generated from {sample.sampleSize} filtered matches;
      {' '}{sample.coveredChampionCount} of {sample.championCount} champions detailed.
      {' '}Generated {new Date(data.generatedAt * 1000).toLocaleString()}.
      {' '}Check claims against the statistics above. Changing the sample or filters clears this analysis.</p>
  </div>;
}
