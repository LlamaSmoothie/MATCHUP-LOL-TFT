import React from 'react';

export default function MatchStatistics({ match }) {
  const value = (n, suffix = '') => Number.isFinite(n) ? `${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}` : 'Unavailable';
  const { context, combat, economy, vision, objectives, sustain } = match;
  const contextText = (key) => typeof context[key] === 'string' ? context[key] : 'Unknown';
  const teams = [match.team, ...(Array.isArray(match.opposingTeams) ? match.opposingTeams : [])];
  const metrics = [
    ['Duration', value(context.durationSeconds, ' sec')],
    ['Kills / deaths / assists', [combat.kills, combat.deaths, combat.assists].map((n) => value(n)).join(' / ')],
    ['CS / minute', value(economy.csPerMinute)], ['Gold / minute', value(economy.goldPerMinute)],
    ['Champion damage', value(combat.damageToChampions)], ['Damage / minute', value(combat.damagePerMinute)],
    ['Kill participation', value(combat.killParticipationPercent, '%')],
    ['Team damage share', value(combat.teamDamageSharePercent, '%')],
    ['Vision score', value(vision.score)], ['Wards placed / cleared', [vision.wardsPlaced, vision.wardsCleared].map((n) => value(n)).join(' / ')],
    ['Objective damage', value(objectives.damageToObjectives)], ['Turret takedowns', value(objectives.turretTakedowns)],
    ['Damage taken', value(sustain.damageTaken)], ['Time dead', value(sustain.timeDeadSeconds, ' sec')],
  ];
  return <section className="match-statistics">
    <h3>Match statistics</h3>
    <p className="stats-note">{contextText('queue')} · {contextText('result')} · Patch {contextText('patch')} · Role: {contextText('role')}</p>
    <dl>{metrics.map(([label, metric]) => <div key={label}><dt>{label}</dt><dd>{metric}</dd></div>)}</dl>
    <div className="ai-team-scroll" tabIndex={0} role="region" aria-label="Match team totals">
      <table className="ai-team-table">
        <caption>Team context</caption>
        <thead><tr>{['Team', 'Kills', 'Gold', 'Champion damage', 'Towers', 'Dragons'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
        <tbody>{teams.map((team, index) => <tr key={index}>
          <th scope="row">{index === 0 ? 'Your team' : `Opposing team ${index}`}</th>
          {[team?.kills, team?.goldEarned, team?.totalDamageDealtToChampions,
            team?.objectives?.tower, team?.objectives?.dragon].map((n, column) => <td key={column}>{value(n)}</td>)}
        </tr>)}</tbody>
      </table>
    </div>
    <p className="stats-note">Team totals provide context for this game. Missing values are unavailable, not zero.
      Objective damage does not establish objective participation.</p>
  </section>;
}
