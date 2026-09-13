import React from 'react';
import { Sparkles, LoaderCircle, ArrowUpRight } from 'lucide-react';
import { createAnalysis } from './analysis.js';

export default function AiAnalysis({ request, disabled = false }) {
  const [store] = React.useState(() => createAnalysis());
  const [expanded, setExpanded] = React.useState(false);
  const { data, error, loading } = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const titleId = React.useId();
  React.useEffect(() => () => store.cancel(), [store]);
  return <section className="ai-analysis" aria-labelledby={titleId} aria-busy={loading}>
    <div className="stats-heading">
      <h3 id={titleId}><Sparkles size={19} aria-hidden="true" /> AI match review</h3>
      <button type="button" className="stats-button"
        disabled={loading || disabled}
        aria-expanded={data ? expanded : undefined}
        aria-controls={data ? `${titleId}-result` : undefined}
        onClick={() => {
          if (data) setExpanded(!expanded);
          else { setExpanded(true); store.run(request); }
        }}>
        {loading ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : !data && <ArrowUpRight size={15} aria-hidden="true" />}
        {loading ? 'Analyzing…' : data ? (expanded ? 'Hide insights' : 'Show insights') : error ? 'Retry analysis' : 'Analyze this match'}
      </button>
    </div>
    {!data && <p className="stats-note">Review combat, economy, vision and objectives from this game.
      On click, match statistics and team totals are sent to OpenAI, along with available timeline checkpoints and events. Player identifiers are excluded.</p>}
    {disabled && <p className="stats-note">AI review will be ready when the timeline request finishes.</p>}
    {loading && <p role="status">Reviewing this match. Your history remains available.</p>}
    {error && <p className="ai-error" role="alert">{error}</p>}
    {data && <div id={`${titleId}-result`} hidden={!expanded}><AnalysisResult data={data} /></div>}
  </section>;
}

export function AnalysisResult({ data }) {
  const { analysis } = data;
  return <div className="ai-result">
    <p>{analysis.summary}</p>
    <div className="ai-result-columns">
      {[['observations', 'What the match data shows'], ['reviewSuggestions', 'Questions for this replay'],
        ['limitations', 'Limits of this analysis']].map(([key, title]) => <div key={key}>
        <h4>{title}</h4><ul>{analysis[key].map((text, index) => <li key={index}>{text}</li>)}</ul>
      </div>)}
    </div>
    <p className="stats-note">AI-generated for this match on {new Date(data.generatedAt * 1000).toLocaleString()}.
      {' '}{data.match?.timeline?.available ? 'Includes sampled timeline data and selected events.' : 'Based on end-of-game totals; timeline data is unavailable.'}
      {' '}Replay video is unavailable. Check claims against the match data.</p>
  </div>;
}
