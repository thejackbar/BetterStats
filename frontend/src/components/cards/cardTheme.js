// Looks for the collectable cards: one entry per rarity tier and one per kind of special card, so a
// special card never reads as a recoloured regular one. Plain data, no React.

export const TIER_ORDER = ['common', 'rare', 'epic', 'legendary', 'special']

// `frame` is the border gradient round the card, `ink` the rarity colour used on the card, `glow` the
// colour of the light a reveal throws.
export const TIERS = {
  common: {
    label: 'Common',
    frame: 'linear-gradient(145deg, #1b2226, #050a0c 55%, #1b2226)',
    ink: '#e5e7eb', glow: '#94a3b8', foil: false,
  },
  rare: {
    label: 'Rare',
    frame: 'linear-gradient(145deg, #f8fafc 0%, #9aa5b1 30%, #e5e9ee 55%, #8b97a3 80%, #f1f5f9 100%)',
    ink: '#dbe4ee', glow: '#cbd5e1', foil: false,
  },
  epic: {
    label: 'Epic',
    frame: 'linear-gradient(145deg, #fff3b0 0%, #e8a317 28%, #fde68a 52%, #b8730a 78%, #ffe9a0 100%)',
    ink: '#fcd34d', glow: '#f59e0b', foil: false,
  },
  legendary: {
    label: 'Legendary',
    frame: 'conic-gradient(from 0deg, #ff6ec7, #ffd86e, #6effc1, #6ec8ff, #b06eff, #ff6ec7)',
    ink: '#ffffff', glow: '#c084fc', foil: true,
  },
  special: {
    label: 'Special',
    frame: 'conic-gradient(from 0deg, #ffffff, #7dd3fc, #f0abfc, #fde68a, #ffffff)',
    ink: '#ffffff', glow: '#7dd3fc', foil: true,
  },
}

// A special card's own design. `panel` is the card's background, `accent` its big colour, `on` the
// text colour that reads on it, `pattern` a layer behind the player.
export const SPECIALS = {
  century: {
    label: 'Century', tag: 'Ton',
    panel: 'linear-gradient(165deg, #fde68a 0%, #d99a14 38%, #7c4a03 100%)', accent: '#fff4c2', on: '#2a1802',
    band: 'linear-gradient(180deg, #fde68a, #e0a417)',
    pattern: 'repeating-conic-gradient(from 0deg at 50% 38%, rgba(255,255,255,.22) 0deg 6deg, transparent 6deg 18deg)',
  },
  fifty: {
    label: 'Half century', tag: 'Fifty',
    panel: 'linear-gradient(165deg, #f3b07a 0%, #c0652b 42%, #4a1d09 100%)', accent: '#ffe2c8', on: '#2a0f03',
    band: 'linear-gradient(180deg, #f6b988, #cf7332)',
    pattern: 'repeating-linear-gradient(115deg, rgba(255,255,255,.14) 0 10px, transparent 10px 26px)',
  },
  five_for: {
    label: 'Five wicket haul', tag: 'Five-for',
    panel: 'linear-gradient(165deg, #c4a1ff 0%, #7c3aed 42%, #25104f 100%)', accent: '#efe4ff', on: '#ffffff',
    band: 'linear-gradient(180deg, #8b5cf6, #4c1d95)',
    pattern: 'repeating-linear-gradient(90deg, rgba(255,255,255,.16) 0 5px, transparent 5px 34px)',
  },
  hat_trick: {
    label: 'Hat-trick', tag: 'Hat-trick',
    panel: 'linear-gradient(165deg, #ff6b6b 0%, #b91c1c 40%, #1a0707 100%)', accent: '#ffe0e0', on: '#ffffff',
    band: 'linear-gradient(180deg, #ef4444, #7f1d1d)',
    pattern: 'radial-gradient(circle at 50% 40%, rgba(255,255,255,.25) 0 36px, transparent 37px), radial-gradient(circle at 20% 55%, rgba(255,255,255,.14) 0 22px, transparent 23px), radial-gradient(circle at 80% 55%, rgba(255,255,255,.14) 0 22px, transparent 23px)',
  },
  debut: {
    label: 'Debut', tag: 'Debut',
    panel: 'linear-gradient(165deg, #ecfdf5 0%, #34d399 38%, #064e3b 100%)', accent: '#ffffff', on: '#022c22',
    band: 'linear-gradient(180deg, #86efc0, #10b981)',
    pattern: 'repeating-radial-gradient(circle at 50% 100%, rgba(255,255,255,.2) 0 4px, transparent 4px 22px)',
  },
  games: {
    label: 'Games milestone', tag: 'Milestone',
    // Bronze, silver, gold and platinum by how many games.
    tiers: [
      { upTo: 50, panel: 'linear-gradient(165deg, #e6a875 0%, #a8602d 45%, #3b1b0a 100%)', band: 'linear-gradient(180deg, #ebb585, #b86f3a)', accent: '#ffe2c8', on: '#2a0f03' },
      { upTo: 100, panel: 'linear-gradient(165deg, #ffffff 0%, #aab4c0 42%, #4b5563 100%)', band: 'linear-gradient(180deg, #ffffff, #c4ccd6)', accent: '#ffffff', on: '#111827' },
      { upTo: 200, panel: 'linear-gradient(165deg, #fde68a 0%, #d99a14 40%, #6b3f02 100%)', band: 'linear-gradient(180deg, #fde68a, #e0a417)', accent: '#fff4c2', on: '#2a1802' },
      { upTo: Infinity, panel: 'linear-gradient(165deg, #e0f2fe 0%, #38bdf8 38%, #0c2a4a 100%)', band: 'linear-gradient(180deg, #e0f2fe, #7dd3fc)', accent: '#ffffff', on: '#06203a' },
    ],
    pattern: 'repeating-linear-gradient(45deg, rgba(255,255,255,.15) 0 3px, transparent 3px 14px)',
  },
  runs_milestone: {
    label: 'Runs milestone', tag: 'Runs',
    panel: 'linear-gradient(165deg, #bae6fd 0%, #0ea5e9 40%, #0c3a5e 100%)', accent: '#ffffff', on: '#04263d',
    band: 'linear-gradient(180deg, #8bd8fd, #0b8ad0)',
    pattern: 'repeating-linear-gradient(0deg, rgba(255,255,255,.16) 0 3px, transparent 3px 18px)',
  },
  wickets_milestone: {
    label: 'Wickets milestone', tag: 'Wickets',
    panel: 'linear-gradient(165deg, #fbcfe8 0%, #db2777 42%, #500724 100%)', accent: '#ffffff', on: '#ffffff',
    band: 'linear-gradient(180deg, #ec4899, #9d174d)',
    pattern: 'repeating-linear-gradient(90deg, rgba(255,255,255,.16) 0 4px, transparent 4px 26px)',
  },
  dismissals_milestone: {
    label: 'Dismissals milestone', tag: 'Dismissals',
    panel: 'linear-gradient(165deg, #ecfccb 0%, #84cc16 40%, #1a2e05 100%)', accent: '#ffffff', on: '#14230a',
    band: 'linear-gradient(180deg, #c3f56a, #6aa812)',
    pattern: 'radial-gradient(circle at 50% 100%, rgba(255,255,255,.22) 0 40px, transparent 41px), radial-gradient(circle at 50% 100%, rgba(255,255,255,.14) 0 80px, transparent 81px)',
  },
  award: {
    label: 'Club award', tag: 'Award',
    panel: null, // the club's own colours
    accent: '#ffffff', on: '#ffffff',
    pattern: 'radial-gradient(ellipse at 50% 30%, rgba(255,255,255,.28), transparent 62%)',
  },
}

// Dark ink on a light colour, white on a dark one.
function onInk(hex) {
  if (!hex || hex[0] !== '#' || hex.length !== 7) return '#ffffff'
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#050a0c' : '#ffffff'
}

export function specialLook(card, accent) {
  const s = SPECIALS[card.special_kind] || SPECIALS.award
  if (card.special_kind === 'games') {
    const n = Number(card.detail?.games) || 0
    const t = s.tiers.find((x) => n <= x.upTo)
    return { ...s, ...t }
  }
  if (!s.panel) {
    return {
      ...s,
      panel: `linear-gradient(165deg, color-mix(in srgb, ${accent} 70%, #fff) 0%, ${accent} 42%, color-mix(in srgb, ${accent} 30%, #000) 100%)`,
      band: `linear-gradient(180deg, ${accent}, color-mix(in srgb, ${accent} 70%, #000))`,
      on: onInk(accent),
    }
  }
  return s
}

// The big figure on a special card and the line under it.
export function specialHeadline(card) {
  const d = card.detail || {}
  switch (card.special_kind) {
    case 'century':
    case 'fifty':
      return { big: `${d.runs ?? ''}${d.not_out ? '*' : ''}`, sub: d.balls ? `off ${d.balls} balls` : '' }
    case 'five_for':
      return { big: `${d.wickets ?? 5}/${d.runs ?? ''}`, sub: d.overs ? `off ${Number(d.overs)} overs` : '' }
    case 'hat_trick':
      return { big: 'HAT-TRICK', sub: d.season ? String(d.season) : '', small: true }
    case 'debut':
      return { big: 'DEBUT', sub: 'First game for the club', small: true }
    case 'games':
      return { big: String(d.games ?? ''), sub: 'games for the club' }
    case 'runs_milestone':
      return { big: Number(d.threshold || 0).toLocaleString('en-AU'), sub: 'career runs' }
    case 'wickets_milestone':
      return { big: Number(d.threshold || 0).toLocaleString('en-AU'), sub: 'career wickets' }
    case 'dismissals_milestone':
      return { big: Number(d.threshold || 0).toLocaleString('en-AU'), sub: 'career dismissals' }
    case 'award':
      return { big: card.title || 'Award', sub: [d.season, d.grade].filter(Boolean).join(' · '), small: true, long: true }
    default:
      return { big: card.title || '', sub: '' }
  }
}

export function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

// Each pack type's own look, so a Duck Pack is never mistaken for a weekly one.
export const PACKS = {
  starter: { label: 'Starter pack', line: 'Welcome to the club', a: '#e2e8f0', b: '#64748b', on: '#0f172a' },
  weekly: { label: 'Weekly pack', line: 'Fresh this week', a: null, b: null, on: null }, // the club's colours
  runs: { label: 'Runs pack', line: 'Earned with the bat', a: '#fde68a', b: '#b45309', on: '#2a1802' },
  wickets: { label: 'Wickets pack', line: 'Earned with the ball', a: '#c4a1ff', b: '#4c1d95', on: '#ffffff' },
  dismissals: { label: 'Dismissals pack', line: 'Earned in the field', a: '#86efac', b: '#14532d', on: '#052e16' },
  duck: { label: 'Duck pack', line: 'Better luck next time', a: '#fef08a', b: '#ca8a04', on: '#3b2a00' },
}

export const sortKeys = [
  { key: 'recent', label: 'Newest first' },
  { key: 'name', label: 'A to Z' },
  { key: 'rarity', label: 'Rarity' },
  { key: 'matches', label: 'Matches' },
  { key: 'runs', label: 'Runs' },
  { key: 'bat_avg', label: 'Batting average' },
  { key: 'wickets', label: 'Wickets' },
  { key: 'bowl_avg', label: 'Bowling average' },
  { key: 'dismissals', label: 'Dismissals' },
]
