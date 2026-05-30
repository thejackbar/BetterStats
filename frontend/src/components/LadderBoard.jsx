import { useState } from 'react'

// Shared per-team ladder rendering for the admin tab and the public page.
// `teams` is the array from /ladders/teams or /ladders/public/{slug}; each team
// carries `views` (Overall / 2 Day+ / One Day), each with API-defined columns.

function fmtVal(v) {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'number' && !Number.isInteger(v)) return v.toFixed(3)
  return String(v)
}

function pickDefaultView(views) {
  const overall = views.findIndex(v => /overall/i.test(v.name))
  return overall >= 0 ? overall : 0
}

function TeamLadder({ team, navFor }) {
  const views = team.views || []
  const [vi, setVi] = useState(() => pickDefaultView(views))
  const view = views[vi]
  const rows = view?.rows || []
  const nav = navFor ? navFor(team) : null

  return (
    <div className="pb-card overflow-hidden">
      <div className="px-4 py-2.5 border-b pb-hairline flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-sm truncate">{team.team_name}</div>
          {team.grade_name && <div className="font-mono text-[10px] text-pb-faint">{team.grade_name}</div>}
        </div>
        {views.length > 1 && (
          <div className="flex gap-1 shrink-0">
            {views.map((v, i) => (
              <button key={v.name} onClick={() => setVi(i)}
                className={`font-mono text-[9px] px-1.5 py-0.5 rounded border transition-colors ${i === vi ? 'bg-pb-accent/15 text-pb-accent border-pb-accent/40' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}>
                {v.name}
              </button>
            ))}
          </div>
        )}
      </div>
      {nav && <div className="px-4 py-2 border-b pb-hairline flex flex-wrap gap-2">{nav}</div>}
      {!team.available || rows.length === 0 ? (
        <div className="px-4 py-6 text-center text-pb-faintest text-sm">Ladder not available for this grade yet.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-pb-faintest font-mono text-[9px] uppercase tracking-wide2 border-b pb-hairline">
                <th className="text-left px-2 py-1.5 w-8">#</th>
                <th className="text-left px-1 py-1.5">Team</th>
                {view.columns.map(c => (
                  <th key={c.id} className={`text-right px-1.5 py-1.5 ${c.id === 'competitionPoints' ? 'font-semibold' : ''}`}>{c.heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.team_id || r.team_name || i}
                  className={`border-t pb-hairline ${r.is_club ? 'bg-pb-accent/10 font-medium' : ''}`}>
                  <td className="px-2 py-1.5 font-mono text-[11px] text-pb-faintest">{r.rank ?? i + 1}</td>
                  <td className="px-1 py-1.5 truncate">
                    {r.team_name}
                    {r.is_club && <span className="ml-1.5 font-mono text-[9px] text-pb-accent">● us</span>}
                  </td>
                  {view.columns.map(c => (
                    <td key={c.id} className={`px-1.5 py-1.5 text-right tabular-nums ${c.id === 'competitionPoints' ? 'font-semibold' : 'text-pb-faint'}`}>
                      {fmtVal(r.stats?.[c.id])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function LadderBoard({ teams, navFor }) {
  if (!teams || teams.length === 0) {
    return <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">No team ladders to show.</div>
  }
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      {teams.map(t => <TeamLadder key={t.team_id} team={t} navFor={navFor} />)}
    </div>
  )
}
