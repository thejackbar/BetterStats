// Data step for the Ladder & Leaders post type: which team's ladder, which
// ladder view, which opponent for Head to Head, and which leaderboard (stat,
// season, grade) for Stat Leaders. The editor holds the state; this only shows
// it and calls back.
const sel = 'h-8 w-full px-2 rounded-md border pb-hairline2 bg-pb-surface2 text-pb-text text-[12px]'
const Label = ({ children }) => <div className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1">{children}</div>

export default function StandingsControls({ s, ladders, teamEntry, seasons = [], onPatch, onRetry }) {
  const teams = ladders && ladders.teams ? ladders.teams : []
  const views = teamEntry?.views || []
  const view = views[s.viewIdx] || views[0]
  const rows = view?.rows || []
  return (
    <div className="flex flex-col gap-4" data-testid="standings-controls">
      <div>
        <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Ladder</h2>
        {ladders === 'loading' && <p className="text-[11px] text-pb-faint">Reading your teams’ ladders…</p>}
        {ladders === 'error' && (
          <p className="text-[11px] text-pb-dim">The ladders could not be read just now. <button className="underline" onClick={onRetry}>Try again</button></p>
        )}
        {ladders && ladders !== 'loading' && ladders !== 'error' && !teams.length && (
          <p className="text-[11px] text-pb-dim">None of your teams is linked to a grade yet, so there is no ladder to read. Link teams to their grades in BetterSelect, Teams.</p>
        )}
        {teams.length > 0 && (
          <div className="flex flex-col gap-2.5">
            <label><Label>Team</Label>
              <select className={sel} value={s.teamKey || ''} data-testid="standings-team" onChange={(e) => onPatch({ teamKey: e.target.value, viewIdx: 0, opp: '' })}>
                {teams.map((t) => <option key={t.team_id} value={t.team_id}>{t.team_name}{t.grade_name ? ` · ${t.grade_name}` : ''}{t.available ? '' : ' (no ladder yet)'}</option>)}
              </select>
            </label>
            {views.length > 1 && (
              <label><Label>Ladder</Label>
                <select className={sel} value={s.viewIdx || 0} onChange={(e) => onPatch({ viewIdx: Number(e.target.value) })}>
                  {views.map((v, i) => <option key={v.name + i} value={i}>{v.name}</option>)}
                </select>
              </label>
            )}
            {teamEntry && !teamEntry.available && <p className="text-[11px] text-pb-dim">Cricket Australia has no ladder for this grade yet. It appears once the grade has results.</p>}
            {rows.length > 0 && (
              <label><Label>Head to Head opponent</Label>
                <select className={sel} value={s.opp || ''} data-testid="standings-opp" onChange={(e) => onPatch({ opp: e.target.value })}>
                  <option value="">Choose a team on this ladder…</option>
                  {rows.filter((r) => !r.is_club).map((r) => <option key={r.team_name} value={r.team_name}>{r.rank != null ? `${r.rank}. ` : ''}{r.team_name}</option>)}
                </select>
              </label>
            )}
          </div>
        )}
      </div>
      <div>
        <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Stat Leaders</h2>
        <div className="grid grid-cols-3 gap-1 mb-2.5">
          {[['batting', 'Runs'], ['bowling', 'Wickets'], ['fielding', 'Dismissals']].map(([k, n]) => (
            <button key={k} data-testid={`leaders-${k}`} onClick={() => onPatch({ leaderKind: k })}
              className={`h-8 rounded-md border text-[11px] ${s.leaderKind === k ? 'text-pb-accent' : 'border-pb-hairline2 bg-pb-surface2 text-pb-dim'}`}
              style={s.leaderKind === k ? { borderColor: 'var(--pb-accent)' } : undefined}>{n}</button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label><Label>Season</Label>
            <select className={sel} value={s.leaderSeason} data-testid="leaders-season" onChange={(e) => onPatch({ leaderSeason: e.target.value })}>
              <option value="">All time</option>
              {seasons.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
          </label>
          <label><Label>Grade</Label>
            <select className={sel} value={s.leaderGrade} data-testid="leaders-grade" onChange={(e) => onPatch({ leaderGrade: e.target.value })}>
              <option value="">Every grade</option>
              {teamEntry?.grade_id && <option value={teamEntry.grade_id}>{teamEntry.grade_name || teamEntry.team_name}</option>}
            </select>
          </label>
        </div>
        <p className="text-[10px] text-pb-faint mt-2 leading-snug">From your club’s own leaderboards, counted the same way as the Stats pages. The grade choice follows the team picked above.</p>
      </div>
    </div>
  )
}
