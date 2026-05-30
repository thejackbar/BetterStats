// Shared per-team ladder rendering for the admin tab and the public page.
// `teams` is the array from /ladders/teams or /ladders/public/{slug}.

function fmtQuot(q) {
  if (q === null || q === undefined || q === '') return '—'
  const n = Number(q)
  return Number.isFinite(n) ? n.toFixed(3) : String(q)
}

function LadderTable({ ladder }) {
  const rows = ladder.rows || []
  if (!ladder.available || rows.length === 0) {
    return <div className="px-4 py-6 text-center text-pb-faintest text-sm">Ladder not available for this grade yet.</div>
  }
  // Only show optional columns when at least one row uses them — keeps it tidy.
  const showT = rows.some(r => r.tied)
  const showNR = rows.some(r => r.no_result)
  const showByes = rows.some(r => r.byes)
  const showQuot = rows.some(r => r.quotient !== null && r.quotient !== undefined && r.quotient !== '')
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-pb-faintest font-mono text-[9px] uppercase tracking-wide2 border-b pb-hairline">
            <th className="text-left px-2 py-1.5 w-8">#</th>
            <th className="text-left px-1 py-1.5">Team</th>
            <th className="text-right px-1.5 py-1.5">P</th>
            <th className="text-right px-1.5 py-1.5">W</th>
            <th className="text-right px-1.5 py-1.5">L</th>
            <th className="text-right px-1.5 py-1.5">D</th>
            {showT && <th className="text-right px-1.5 py-1.5">T</th>}
            {showNR && <th className="text-right px-1.5 py-1.5">NR</th>}
            {showByes && <th className="text-right px-1.5 py-1.5">Bye</th>}
            <th className="text-right px-1.5 py-1.5 font-semibold">Pts</th>
            {showQuot && <th className="text-right px-1.5 py-1.5">Quot</th>}
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
              <td className="px-1.5 py-1.5 text-right tabular-nums">{r.played}</td>
              <td className="px-1.5 py-1.5 text-right tabular-nums">{r.won}</td>
              <td className="px-1.5 py-1.5 text-right tabular-nums">{r.lost}</td>
              <td className="px-1.5 py-1.5 text-right tabular-nums">{r.drawn}</td>
              {showT && <td className="px-1.5 py-1.5 text-right tabular-nums">{r.tied}</td>}
              {showNR && <td className="px-1.5 py-1.5 text-right tabular-nums">{r.no_result}</td>}
              {showByes && <td className="px-1.5 py-1.5 text-right tabular-nums">{r.byes}</td>}
              <td className="px-1.5 py-1.5 text-right tabular-nums font-semibold">{r.points}</td>
              {showQuot && <td className="px-1.5 py-1.5 text-right tabular-nums text-pb-faint">{fmtQuot(r.quotient)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function LadderBoard({ teams }) {
  if (!teams || teams.length === 0) {
    return <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">No team ladders to show.</div>
  }
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      {teams.map(t => (
        <div key={t.team_id} className="pb-card overflow-hidden">
          <div className="px-4 py-2.5 border-b pb-hairline">
            <div className="font-semibold text-sm truncate">{t.team_name}</div>
            {t.grade_name && <div className="font-mono text-[10px] text-pb-faint">{t.grade_name}</div>}
          </div>
          <LadderTable ladder={t} />
        </div>
      ))}
    </div>
  )
}
