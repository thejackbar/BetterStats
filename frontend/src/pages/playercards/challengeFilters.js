// Filtering the cards a player can pick for a squad challenge. Pure, so the screen and the checks share one definition.
// Only player cards carry a rating (1 to 99). Special cards have none, so a narrowed rating range leaves them out.
import { CATEGORIES } from '../../components/cards/CardGallery'

export const RATING_MIN = 1
export const RATING_MAX = 99

const CAT_OF = Object.fromEntries(CATEGORIES.flatMap((c) => c.kinds.map((k) => [k, c.key])))
const TIER_RANK = { special: 0, legendary: 1, epic: 2, rare: 3, common: 4 }

export const DEFAULT_FILTERS = { tier: 'all', type: 'all', role: '', lo: RATING_MIN, hi: RATING_MAX, q: '', fits: false, sort: 'best' }

export const SORTS = [['best', 'Best first'], ['rating_desc', 'Highest rating'], ['rating_asc', 'Lowest rating'], ['name', 'Name A to Z']]

// Clamp a typed rating to 1..99; an empty or unreadable box falls back to the end of the range it belongs to.
export function clampRating(v, fallback) {
  const n = Math.round(Number(v))
  if (v === '' || v == null || !Number.isFinite(n)) return fallback
  return Math.min(RATING_MAX, Math.max(RATING_MIN, n))
}

export const ratingNarrowed = (f) => f.lo > RATING_MIN || f.hi < RATING_MAX

// Does one card, on its own, meet the rules that are about a single card? Rules about the whole squad (count, minimums per
// tier or role, squad rating, cards of one player) cannot be judged card by card and are left to the server's check.
export function fitsRules(c, rules) {
  if (!rules) return true
  if (rules.kinds === 'players' && c.kind !== 'player') return false
  if (rules.kinds === 'specials' && c.kind !== 'special') return false
  if (rules.tiers_only?.length && !rules.tiers_only.includes(c.tier)) return false
  if (rules.roles?.length && !rules.roles.includes(c.role)) return false
  if (rules.special_kinds?.length && c.kind === 'special' && !rules.special_kinds.includes(c.special_kind)) return false
  if (rules.players?.length && !rules.players.includes(c.player_id)) return false
  return true
}

// Whether the rules say anything about a single card, so the "fits" filter has something to do.
export const hasCardRules = (rules) => !!(rules && ((rules.kinds && rules.kinds !== 'any') || rules.tiers_only?.length || rules.roles?.length || rules.special_kinds?.length || rules.players?.length))

export function filterChallengeCards(cards, f, rules) {
  const words = (f.q || '').trim().toLowerCase().split(/\s+/).filter(Boolean)
  const narrowed = ratingNarrowed(f)
  const out = cards.filter((c) => {
    if (f.tier !== 'all' && c.tier !== f.tier) return false
    if (f.type === 'player' && c.kind !== 'player') return false
    if (f.type === 'special' && c.kind !== 'special') return false
    if (f.type !== 'all' && f.type !== 'player' && f.type !== 'special' && (c.kind !== 'special' || CAT_OF[c.special_kind] !== f.type)) return false
    if (f.role && (c.role || 'none') !== f.role) return false
    if (narrowed) {
      if (c.kind !== 'player' || c.rarity == null) return false
      if (c.rarity < f.lo || c.rarity > f.hi) return false
    }
    if (f.fits && !fitsRules(c, rules)) return false
    if (words.length) {
      const d = c.detail || {}
      const hay = `${c.name} ${c.title || ''} ${d.season || ''} ${d.grade || ''}`.toLowerCase()
      if (!words.every((w) => hay.includes(w))) return false
    }
    return true
  })
  const rating = (c) => (c.kind === 'player' && c.rarity != null ? c.rarity : null)
  const byName = (a, b) => (a.name || '').localeCompare(b.name || '')
  const sorters = {
    best: (a, b) => ((TIER_RANK[a.tier] ?? 5) - (TIER_RANK[b.tier] ?? 5)) || ((rating(b) ?? 0) - (rating(a) ?? 0)) || byName(a, b),
    // A card with no rating goes to the end either way.
    rating_desc: (a, b) => ((rating(a) == null) - (rating(b) == null)) || ((rating(b) ?? 0) - (rating(a) ?? 0)) || byName(a, b),
    rating_asc: (a, b) => ((rating(a) == null) - (rating(b) == null)) || ((rating(a) ?? 0) - (rating(b) ?? 0)) || byName(a, b),
    name: (a, b) => byName(a, b) || ((TIER_RANK[a.tier] ?? 5) - (TIER_RANK[b.tier] ?? 5)),
  }
  return out.sort(sorters[f.sort] || sorters.best)
}

// The chips worth drawing for these cards: only types and roles some card actually has.
export function chipCounts(cards) {
  const out = { player: 0, special: 0, cats: {}, roles: {}, none: 0 }
  for (const c of cards) {
    if (c.kind === 'player') out.player += 1
    if (c.kind === 'special') { out.special += 1; const k = CAT_OF[c.special_kind]; if (k) out.cats[k] = (out.cats[k] || 0) + 1 }
    if (c.role) out.roles[c.role] = (out.roles[c.role] || 0) + 1; else out.none += 1
  }
  return out
}
