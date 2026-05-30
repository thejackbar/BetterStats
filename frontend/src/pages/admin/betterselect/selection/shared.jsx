// Shared constants + tiny presentational helpers for the Selection screen,
// imported by the page container and its TeamSheet / PlayerPool / SelectionFilters
// subcomponents. Kept in its own module (not the page) so the components don't
// import back from the page, which would be circular.
import { AVAILABILITY, AVAIL_STATUSES } from '../../../../lib/availability'

// Row state → tint. Order of precedence handled in rowState().
export const ROW_TINT = {
  CLASH:       'bg-pb-red/15',
  UNAVAILABLE: 'bg-pb-red/5',
  AVAILABLE:   'bg-pb-accent/5',
  MAYBE:       'bg-amber-400/5',
  DORMANT:     'bg-amber-400/[0.03]',
  NONE:        '',
}
export const AVAIL_META = Object.fromEntries(
  AVAIL_STATUSES.map((s) => [s, { dot: AVAILABILITY[s].dot, label: AVAILABILITY[s].label }]),
)
export const AVAIL_RANK = Object.fromEntries(AVAIL_STATUSES.map((s) => [s, AVAILABILITY[s].rank]))
export const SKILL_LABELS = { BAT: 'Batsman', BWL: 'Bowler', ALL: 'All Rounder', WKT: 'Wicketkeeper' }
export const BAT_HANDS = { LEFT: 'Left handed', RIGHT: 'Right handed' }
export const BOWL_ACTIONS = { RIGHT_ARM: 'Right arm', LEFT_ARM: 'Left arm' }
export const BOWL_TYPES = {
  FAST: 'Fast', FAST_MEDIUM: 'Fast medium', MEDIUM: 'Medium',
  MEDIUM_FAST: 'Medium fast', FINGER_SPIN: 'Finger spinner', WRIST_SPIN: 'Wrist spinner',
}

export function Avatar({ p }) {
  if (p.photo_url) return <img src={p.photo_url} alt="" className="w-7 h-7 rounded-full object-cover bg-pb-surface2" />
  const initials = (p.display_name || '?').split(/[ ,]+/).filter(Boolean).slice(0, 2).map(s => s[0]).join('').toUpperCase()
  return <span className="w-7 h-7 rounded-full bg-pb-surface2 text-pb-faint text-[10px] font-mono flex items-center justify-center">{initials}</span>
}

export function roleText(p) {
  return p.skill_positions?.length ? p.skill_positions.join(' ') : (p.player_role || '—')
}

// Tint a pool row by its most salient state.
export function rowState(p) {
  if (p.clash?.length > 0) return 'CLASH'
  if (p.availability === 'UNAVAILABLE') return 'UNAVAILABLE'
  if (p.availability === 'AVAILABLE') return 'AVAILABLE'
  if (p.availability === 'MAYBE') return 'MAYBE'
  if (p.is_dormant) return 'DORMANT'
  return 'NONE'
}
