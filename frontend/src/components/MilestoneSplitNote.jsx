// The one line that says a milestone figure counts (or leaves out) a player's
// junior matches, and what the other figure is.
//
// A club asked for a senior/junior switch on Milestones. The milestone emails
// cannot press a switch, so the backend works it out instead: every milestone
// counts what the player's own profile counts, and a player with junior AND
// open-age records carries both figures (`junior_split`). Where only the other
// figure is close to a milestone it arrives as its own entry, marked `variant`
// and named by `counts`. This draws that, identically on every screen.
//
// Renders nothing for a player whose record has nothing to split, which is
// most of them: a note on every row teaches people to stop reading notes.

const UNITS = { runs: 'runs', wickets: 'wickets', matches: 'matches', catches: 'catches' }

export function milestoneSplitText(m) {
  const split = m?.junior_split
  if (!split) return null
  const unit = UNITS[m.type] || ''
  const n = (v) => `${Number(v || 0).toLocaleString()}${unit ? ` ${unit}` : ''}`
  const w = split.with_junior
  const wo = split.without_junior
  if (m.counts === 'with_junior') return `Includes junior matches · ${n(wo)} without them`
  if (m.counts === 'without_junior') return `Excludes junior matches · ${n(w)} with them`
  return `${n(w)} with junior matches · ${n(wo)} without`
}

export default function MilestoneSplitNote({ m, className = '' }) {
  const t = milestoneSplitText(m)
  if (!t) return null
  return (
    <span
      data-testid="milestone-split"
      className={`block font-mono text-[10px] text-pb-dim tracking-wide2 ${className}`}
      title="Worked out from the player's own record: the same milestone counted with and without the junior matches they played."
    >
      {t}
    </span>
  )
}
