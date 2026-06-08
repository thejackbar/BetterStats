// Selection-screen domain helpers — the "genuinely useful one-liner" that
// replaces the old hardcoded positional hints (Opener / First drop / …), plus
// the bowling/form classifiers the expanded pool filters key on.
//
// Role + style come straight from the player's real attributes via the shared
// playerAttributes label maps, so the selection board and the public profile
// never drift. Form is a quiet last-4 trend computed server-side
// (selection_pool.py) — `form` is the word, `recent` is the sparkline series.
import { bowlingLabel, battingHandShort } from '../../../lib/playerAttributes'

const ROLE_NOUN = {
  'Batter': 'Batter',
  'Bowler': 'Bowler',
  'All Rounder': 'All-rounder',
  'Wicketkeeper': 'Keeper',
  'Wicketkeeper-Batter': 'Keeper-bat',
}

export function roleNoun(p) {
  if (p?.is_opening_batsman && p?.player_role === 'Batter') return 'Opening bat'
  return ROLE_NOUN[p?.player_role] || p?.player_role || 'Player'
}

// Human bowling style ("Off spin", "Right-arm fast"), or null if they don't bowl.
export function bowlLabel(p) {
  const l = bowlingLabel(p?.bowling_action, p?.bowling_type)
  return l && l !== '—' ? l : null
}

// Full descriptive line: "All-rounder · RHB · Off spin".
export function roleLine(p) {
  const bits = [roleNoun(p)]
  const hand = battingHandShort(p?.batting_hand)
  if (hand) bits.push(hand)
  const bowl = bowlLabel(p)
  if (bowl) bits.push(bowl)
  return bits.join(' · ')
}

// Compact style only (no role noun): "RHB · Off spin".
export function styleLine(p) {
  const bits = []
  const hand = battingHandShort(p?.batting_hand)
  if (hand) bits.push(hand)
  const bowl = bowlLabel(p)
  if (bowl) bits.push(bowl)
  return bits.join(' · ')
}

// Bowling classification for the Pace/Spin/Doesn't-bowl filter.
export function classifyBowl(p) {
  if (!p?.bowling_action && !p?.bowling_type) return 'none'
  const t = (p?.bowling_type || '').toUpperCase()
  return /SPIN|ORTHODOX/.test(t) ? 'spin' : 'pace'
}
export const BOWL_KINDS = [
  { value: 'pace', label: 'Pace' },
  { value: 'spin', label: 'Spin' },
  { value: 'none', label: "Doesn't bowl" },
]

// Form word → presentation. Backend sends hot / warm / steady / quiet / cold or
// null (no recent sample). Colours are semantic, never the club accent.
export const FORM_META = {
  hot: { label: 'Hot', token: 'var(--pb-positive)' },
  warm: { label: 'In form', token: 'var(--pb-positive)' },
  steady: { label: 'Steady', token: 'var(--pb-dim)' },
  quiet: { label: 'Quiet', token: 'var(--pb-faint)' },
  cold: { label: 'Cold', token: 'var(--pb-faint)' },
}
export function formMeta(p) { return FORM_META[p?.form] || null }

// Filter bucket (cold collapses into the "Out of nick" bucket).
export function formBucket(p) {
  const f = p?.form
  if (f === 'hot' || f === 'warm' || f === 'steady') return f
  if (f === 'quiet' || f === 'cold') return 'quiet'
  return null
}
export const FORM_BUCKETS = [
  { value: 'hot', label: 'Hot' },
  { value: 'warm', label: 'In form' },
  { value: 'steady', label: 'Steady' },
  { value: 'quiet', label: 'Out of nick' },
]

export const HAND_KINDS = [
  { value: 'RIGHT', label: 'Right-hand' },
  { value: 'LEFT', label: 'Left-hand' },
]

export const SORTS = [
  { value: 'squad', label: 'Squad order' },
  { value: 'form', label: 'Form' },
  { value: 'name', label: 'Name (A–Z)' },
]

// Normalise a recent series to 0..1 bar heights for a mini sparkline.
export function spark(recent) {
  const r = (recent || []).filter((v) => typeof v === 'number')
  if (!r.length) return []
  const max = Math.max(1, ...r)
  return r.map((v) => Math.max(0.16, v / max))
}
