// What a club's recorded milestones become on a post. The editor reads the club's
// own milestone report (the same list as Admin > Milestones, `achieved`), the club
// ticks the ones to feature, and the layouts are handed the result.
//
// Pure functions, so the ticking and the window can be checked without a screen.

export const MILESTONE_WINDOWS = [
  { key: '14', label: 'Last 14 days', days: 14 },
  { key: '30', label: 'Last 30 days', days: 30 },
  { key: '90', label: 'Last 90 days', days: 90 },
  { key: 'year', label: 'This year' },
  { key: 'all', label: 'All time' },
]
export const DEFAULT_MILESTONE_WINDOW = '30'

// One milestone is one player crossing one threshold. The grade is part of the
// key because a player has a games-in-grade milestone for each grade.
export const milestoneKey = (r) => `${r.player_id}:${r.type}:${r.milestone_value}:${r.detail || ''}`

export function milestoneValueText(r) {
  return r.type === 'runs' ? Number(r.milestone_value).toLocaleString('en-AU') : String(r.milestone_value)
}

export function milestoneUnit(r) {
  switch (r.type) {
    case 'runs': return 'Career runs'
    case 'wickets': return 'Career wickets'
    case 'catches': return 'Career catches'
    case 'matches': return 'Club games'
    case 'grade_matches': return r.detail ? `Games in ${r.detail}` : 'Games'
    default: return String(r.type || '')
  }
}

// "2026-10-04" is a calendar day, not a moment: read it as local so it never
// slips a day across the timezone.
function parseDay(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '')
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null
}

export function formatMilestoneDate(iso) {
  const d = parseDay(iso)
  return d ? d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : ''
}

/** Is this milestone inside the window? Undated ones are only in "All time". */
export function inWindow(row, windowKey, today = new Date()) {
  if (windowKey === 'all') return true
  const d = parseDay(row.achieved_at)
  if (!d) return false
  if (windowKey === 'year') return d.getFullYear() === today.getFullYear()
  const w = MILESTONE_WINDOWS.find((x) => x.key === windowKey)
  if (!w?.days) return true
  const from = new Date(today.getFullYear(), today.getMonth(), today.getDate() - w.days)
  return d >= from
}

/** The report's achieved milestones, newest first (undated last), each with its key. */
export function achievedMilestones(report) {
  const rows = (report?.achieved || []).map((r) => ({ ...r, key: milestoneKey(r) }))
  const at = (r) => parseDay(r.achieved_at)?.getTime() ?? -Infinity
  return rows
    .map((r, i) => ({ r, i }))
    .sort((a, b) => (at(b.r) - at(a.r)) || (b.r.milestone_value - a.r.milestone_value) || (a.i - b.i))
    .map((x) => x.r)
}

/** What is ticked to begin with: the newest in the window, up to the layout's room. */
export function defaultPicks(rows, windowKey, max, today = new Date()) {
  return rows.filter((r) => inWindow(r, windowKey, today)).slice(0, max).map((r) => r.key)
}

/** Rows shown in the picker: in the window, matching the name search. */
export function visibleMilestones(rows, windowKey, search, today = new Date()) {
  const words = (search || '').toLowerCase().split(/\s+/).filter(Boolean)
  return rows.filter((r) => inWindow(r, windowKey, today)
    && words.every((w) => (r.player_name || '').toLowerCase().includes(w)))
}
