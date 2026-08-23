/* BetterIQ — scouting-card vocab + "DNA" synthesis.
 *
 * The shared brain behind the manual scouting card (batting & bowling), used for
 * both opposition players and our own. CA gives us no ball-by-ball data, so the
 * "vulnerable to pace short outside off, favours the pull" read is scout-entered;
 * this turns that intel — blended with the dismissal breakdown we DO hold — into a
 * short list of plain-English insight bullets, mirroring a "Dismissal DNA" read.
 *
 * Vocab codes here MUST match backend app/services/scouting_intel.py. */

export const BOWLING_KINDS = {
  PACE: 'Genuine pace',
  FAST_MEDIUM: 'Fast-medium',
  SWING: 'Swing',
  SEAM: 'Seam',
  OFF_SPIN: 'Off spin',
  LEG_SPIN: 'Leg spin',
  LEFT_ARM_ORTHODOX: 'Left-arm orthodox',
  LEFT_ARM_WRIST: 'Left-arm wrist',
  LEFT_ARM_PACE: 'Left-arm pace',
}

export const BAT_SHOTS = {
  PULL: 'Pull', HOOK: 'Hook', CUT: 'Cut', DRIVE: 'Straight drive',
  COVER_DRIVE: 'Cover drive', ON_DRIVE: 'On drive', SWEEP: 'Sweep',
  REVERSE_SWEEP: 'Reverse sweep', LOFT: 'Loft / slog', FLICK: 'Flick',
  GLANCE: 'Glance', DEFENCE: 'Defence', LEAVE: 'Leave',
}

export const BOWL_VARIATIONS = {
  YORKER: 'Yorker', BOUNCER: 'Bouncer', SLOWER_BALL: 'Slower ball',
  OFF_CUTTER: 'Off-cutter', LEG_CUTTER: 'Leg-cutter', INSWING: 'Inswinger',
  OUTSWING: 'Outswinger', DOOSRA: 'Doosra', GOOGLY: 'Googly', ARM_BALL: 'Arm ball',
  TOP_SPINNER: 'Top-spinner', CARROM: 'Carrom ball', KNUCKLE: 'Knuckle ball',
}

export const BOWL_DANGER = {
  NEW_BALL: 'With the new ball', FIRST_CHANGE: 'First change',
  MIDDLE: 'Through the middle', DEATH: 'At the death',
  VS_LHB: 'vs left-handers', VS_RHB: 'vs right-handers', VS_SET: 'Once batters are set',
}

export const ZONE_LENGTHS = ['Full toss', 'Full', 'Good', 'Short']
export const ZONE_LINES = ['Wide off', 'Off stump', 'Stumps', 'Leg stump', 'Down leg']

export const labelList = (codes, map) => (codes || []).map(c => map[c]).filter(Boolean)
export const hasIntel = (intel) => {
  if (!intel) return false
  return Object.values(intel).some(v => (Array.isArray(v) ? v.length : !!v))
}

/* The strongest cell in a length×line grid → a natural phrase ("short balls
   outside off"). Returns null when nothing is marked. */
const _LEN_PHRASE = { 'Full toss': 'full tosses', Full: 'full deliveries', Good: 'good-length balls', Short: 'short balls' }
const _LINE_PHRASE = { 'Wide off': 'outside off', 'Off stump': 'on off stump', Stumps: 'at the stumps', 'Leg stump': 'on leg stump', 'Down leg': 'down the leg side' }
export function topZonePhrase(cells) {
  if (!Array.isArray(cells) || !cells.length) return null
  let best = -1, bi = -1
  for (let i = 0; i < ZONE_LENGTHS.length * ZONE_LINES.length; i++) {
    const v = Number(cells[i]) || 0
    if (v > best) { best = v; bi = i }
  }
  if (best <= 0) return null
  const len = ZONE_LENGTHS[Math.floor(bi / ZONE_LINES.length)]
  const line = ZONE_LINES[bi % ZONE_LINES.length]
  return `${_LEN_PHRASE[len] || len} ${_LINE_PHRASE[line] || line}`
}

/* Dismissal type → a one-line tactical tell (batter's weakness). */
const _DISM_TELL = {
  bowled: 'gets bowled often, attack the stumps',
  lbw: 'falls lbw regularly, bowl straight and full',
  'caught behind': 'nicks off. Feed the channel and stack the cordon',
  caught: 'holes out. Push catchers into the deep',
  'c&b': 'chips it back. Follow through ready',
  stumped: 'can be drawn out. Bring the keeper up',
  'run out': 'suspect between the wickets, pressure the single',
  'hit wicket': 'gets cramped on the back foot',
}

const _norm = (s) => String(s || '').toLowerCase()

/* Build the batting "DNA" — manual intel blended with the held dismissal mix.
   `dismissals` = [{type, count|pct}] from the page (opponent dossier or own deep). */
export function buildBattingDna(intel, dismissals) {
  const out = []
  const i = intel || {}
  // Held data first — the dominant way they actually get out.
  const ds = (dismissals || []).filter(d => d && d.type)
  if (ds.length) {
    const total = ds.reduce((s, d) => s + (d.count ?? d.pct ?? 0), 0)
    const top = ds.slice().sort((a, b) => (b.count ?? b.pct ?? 0) - (a.count ?? a.pct ?? 0))[0]
    const share = total ? (top.count ?? top.pct ?? 0) / total : 0
    const tell = _DISM_TELL[_norm(top.type)]
    if (tell && share >= 0.33) out.push({ tone: 'data', text: `${top.type[0].toUpperCase()}${top.type.slice(1)} is his most common dismissal (${Math.round(share * 100)}%): ${tell}.` })
  }
  const vuln = labelList(i.vuln_bowling, BOWLING_KINDS)
  if (vuln.length) out.push({ tone: 'scout', text: `Vulnerable to ${vuln.join(', ').toLowerCase()}.` })
  const favBowl = labelList(i.fav_bowling, BOWLING_KINDS)
  if (favBowl.length) out.push({ tone: 'scout', text: `Comfortable against ${favBowl.join(', ').toLowerCase()}.` })
  const zone = topZonePhrase(i.zones)
  if (zone) out.push({ tone: 'scout', text: `Struggles with ${zone}.` })
  // A pre-split blob only ever carried one combined "shots" list — read it as
  // risky (the card's framing was "how to get him out") when neither new list
  // has been entered yet, so already-saved intel isn't silently dropped.
  const riskyShots = labelList(i.risky_shots, BAT_SHOTS)
  const favShots = labelList(i.fav_shots, BAT_SHOTS)
  const legacyShots = (!riskyShots.length && !favShots.length) ? labelList(i.shots, BAT_SHOTS) : []
  const risky = riskyShots.length ? riskyShots : legacyShots
  if (risky.length) out.push({ tone: 'scout', text: `Goes after the ${risky.join(', ').toLowerCase()}. Set the trap.` })
  if (favShots.length) out.push({ tone: 'scout', text: `Favours the ${favShots.join(', ').toLowerCase()}.` })
  if (i.weaknesses) out.push({ tone: 'scout', text: i.weaknesses })
  return { bullets: out, plan: i.plan || null, strengths: i.strengths || null }
}

/* Build the bowling "DNA". `wicketMethods` = [{type, count}] of how he takes
   wickets (opponent deep scan / own bowling-deep), optional. */
export function buildBowlingDna(intel, wicketMethods) {
  const out = []
  const i = intel || {}
  const stock = BOWLING_KINDS[i.stock]
  const vars = labelList(i.variations, BOWL_VARIATIONS)
  if (stock || vars.length) {
    const tail = vars.length ? `, with ${vars.join(', ').toLowerCase()}` : ''
    out.push({ tone: 'scout', text: `Bowls ${(stock || 'an unlisted style').toLowerCase()}${tail}.` })
  }
  const wm = (wicketMethods || []).filter(d => d && d.type)
  if (wm.length) {
    const total = wm.reduce((s, d) => s + (d.count ?? d.pct ?? 0), 0)
    const top = wm.slice().sort((a, b) => (b.count ?? b.pct ?? 0) - (a.count ?? a.pct ?? 0))[0]
    const share = total ? (top.count ?? top.pct ?? 0) / total : 0
    if (share >= 0.4) out.push({ tone: 'data', text: `Most of his wickets come ${_norm(top.type) === 'bowled' ? 'bowled' : top.type} (${Math.round(share * 100)}%).` })
  }
  const zone = topZonePhrase(i.zones)
  if (zone) out.push({ tone: 'scout', text: `Attacks ${zone}.` })
  const danger = labelList(i.danger, BOWL_DANGER)
  if (danger.length) out.push({ tone: 'scout', text: `Most dangerous ${danger.join(', ').toLowerCase()}.` })
  if (i.weaknesses) out.push({ tone: 'scout', text: i.weaknesses })
  return { bullets: out, plan: i.plan || null, strengths: i.strengths || null }
}
