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

/* ── Age ──────────────────────────────────────────────────────────────────
 * The pool's `age` is already the club's own answer: the server applies both
 * halves of the rule (ages on at all, and any "juniors only" limit), so a
 * player carrying one is a player this selector is meant to see. That makes
 * the filter a plain read of a value already on the card.
 *
 * Values are a fixed ladder rather than one option per age present, so the
 * control reads the same from week to week and "Under 16" is where a coach
 * expects to find it. The two ends are only OFFERED when the club shows
 * every age — under a limit an adult has no age at all, so "18 and over"
 * would always be empty and "no age shown" would mean "an adult, or someone
 * with no birthday recorded", which is two questions wearing one label. */
export const AGE_UNDER_LADDER = [13, 14, 15, 16, 17, 18, 19]

export function ageFilterOptions(flags) {
  const rule = flags?.age
  if (!rule?.shown) return []
  const limit = rule.under ?? null
  // Only thresholds the club's own limit can actually answer: asking for
  // under-18s when ages stop at 16 would quietly return the under-16s.
  const unders = AGE_UNDER_LADDER.filter((n) => limit == null || n <= limit)
  const opts = unders.map((n) => ({ value: `u${n}`, label: `Under ${n}` }))
  if (limit == null) {
    opts.push({ value: 'adult', label: '18 and over' })
    opts.push({ value: 'none', label: 'No date of birth' })
  }
  return opts
}

export function matchesAge(p, value) {
  if (!value) return true
  if (value === 'none') return p?.age == null
  if (value === 'adult') return p?.age != null && p.age >= 18
  const n = Number(String(value).slice(1))
  return p?.age != null && Number.isFinite(n) && p.age < n
}

export function ageFilterLabel(value, flags) {
  return (ageFilterOptions(flags).find((o) => o.value === value) || {}).label || null
}

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
