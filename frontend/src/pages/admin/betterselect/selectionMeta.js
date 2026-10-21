// Selection-screen domain helpers — the "genuinely useful one-liner" that
// replaces the old hardcoded positional hints (Opener / First drop / …), plus
// the bowling/form classifiers the expanded pool filters key on.
//
// Role + style come straight from the player's real attributes via the shared
// playerAttributes label maps, so the selection board and the public profile
// never drift. Form is a quiet last-4 trend computed server-side
// (selection_pool.py) — `form` is the word, `recent` is the sparkline series.
import { bowlingLabel, battingHandShort } from '../../../lib/playerAttributes'
import { availRank, halfStatus } from '../../../lib/availability'

// A player named in another XI on the same date comes back in one of two ways.
// `clash` is a real clash (refused, or a call-up). `also_in` is a game that can
// be played alongside this one (back to back, or junior against senior): the
// pick is allowed and the card only flags it. Server side: selection_clash.py.
export function alsoIn(p) { return Array.isArray(p?.also_in) ? p.also_in : [] }
export function inAnotherXI(p) { return p?.clash?.length > 0 || alsoIn(p).length > 0 }
export function alsoInLine(p) { return alsoIn(p).map((a) => a.text || a.team_name).join('; ') }
// A player the squad above has not picked that day: the natural first call for
// the grade below. The server decides (selection_pool._drop_in_from) and names
// the squad; this only words it.
export function dropInLine(p) { return p?.drop_in_from ? `Not picked in ${p.drop_in_from}` : '' }
// Another side's UNCONFIRMED draft already names this player that day. Never
// blocks a pick (only a confirmed XI does); it just says someone has plans.
export function inDraftLine(p) { return Array.isArray(p?.in_draft_of) && p.in_draft_of.length ? `In ${p.in_draft_of.join(', ')} draft (not confirmed)` : '' }
// The day tabs a fixture belongs on: its own date, and for a two-day game its
// second weekend too, so both weekends show the game and the two are linked.
export function fixtureTabs(f) {
  const first = f?.played_on || 'tbc'
  return f?.end_on && f?.played_on && f.end_on > f.played_on ? [first, f.end_on] : [first]
}
// " for W2" / " for W1 and W2" for the weeks marked UNAVAILABLE, '' when none.
// `names` is the club's week names ({ w1, w2 }, W1 and W2 by default).
export function unavailableWeeksText(days, names) {
  if (!Array.isArray(days)) return ''
  const n = [names?.w1 || 'W1', names?.w2 || 'W2']
  const w = days.map((d, i) => (d.status === 'UNAVAILABLE' ? n[i] : '')).filter(Boolean)
  if (!w.length) return ''
  return ` for ${w.join(' and ')}`
}
// "Sat 24 Oct" or, for a two-day game, "Sat 24 Oct + Sat 31 Oct".
export function gameDatesLabel(playedOn, endOn) {
  const f = (iso) => {
    try { return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) }
    catch { return iso }
  }
  if (!playedOn) return ''
  return endOn && endOn > playedOn ? `${f(playedOn)} + ${f(endOn)}` : f(playedOn)
}
// The board's default order, mirroring selection_pool._pool_rank: first anyone
// free one weekend of a two-day game and still open to pick (`half_open`), then
// everyone who says they are available and is named nowhere that day, highest squad
// first (`open_seq`: the place of their highest squad in the club). Then the
// fixture's own squad (members, then anyone ranked level with it), players the
// squad above has not picked, the squad below, the rest of the squad above, and
// everyone else.
export function poolRank(p) {
  const base = p?.open_seq != null ? p.open_seq
    : p?.squad_match ? 1000
    : p?.tier === 1 ? 1001
    : p?.drop_in_from ? 1002
    : (p?.tier === 2 || p?.tier === 3) ? 1002 + p.tier
    : 1099
  // Free one weekend of a two-day game and still open to pick: the selector has to
  // decide, so they lead the pool (`half_open`, from the server), squad order kept.
  return p?.half_open ? base - 10000 : base
}

// Where an answer sorts inside a pool bucket: Available, Maybe, then someone free
// the second weekend only (HALF_W2, rank 1.5), then no answer, then Unavailable.
// Ordering only: `availability` stays the combined answer for rules and filters.
export function poolAvailRank(p) {
  return halfStatus(p?.availability_days) === 'HALF_W2' ? availRank('HALF_W2') : availRank(p?.availability)
}

// A player's gender as the filters read it: 'male', 'female', or '' when unrecorded.
export function normGender(g) { const s = String(g || '').toLowerCase(); return s.startsWith('f') ? 'female' : s.startsWith('m') ? 'male' : '' }
export const GENDER_OPTS = [{ value: '', label: 'All' }, { value: 'male', label: 'Men' }, { value: 'female', label: 'Women' }]

export function alsoInTight(p) { return alsoIn(p).some((a) => a.tight) }

// Every word typed must appear somewhere in the name, in any order, so
// "jack bar" finds "Barendse, Jack" and "barendse jack" finds "Jack Barendse".
// A plain substring test failed both: the stored name is "Last, First" and the
// selector types it however they say it. Empty query matches everyone.
export function nameMatches(name, query) {
  const words = String(query || '').toLowerCase().split(/[\s,]+/).filter(Boolean)
  if (!words.length) return true
  const hay = String(name || '').toLowerCase()
  return words.every((w) => hay.includes(w))
}

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
export const AGE_UNDER_LADDER = [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]

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
  { value: 'name', label: 'Surname (A–Z)' },
  { value: 'first', label: 'First name (A–Z)' },
]

// Normalise a recent series to 0..1 bar heights for a mini sparkline.
export function spark(recent) {
  const r = (recent || []).filter((v) => typeof v === 'number')
  if (!r.length) return []
  const max = Math.max(1, ...r)
  return r.map((v) => Math.max(0.16, v / max))
}
