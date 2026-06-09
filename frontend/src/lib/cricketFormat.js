// ── Cricket stat display formatting — single source of truth ─────────────────
//
// Conventions (locked with product owner, Jun 2026). Apply these EVERYWHERE a
// cricket stat is shown so formatting can never drift between surfaces:
//
//  • Averages, strike rates, economy rates & run rate → ALWAYS 2 decimals
//    (e.g. an average of exactly 50 shows "50.00").
//  • Counts (runs, wickets, matches, balls, catches…) → thousands separators
//    (commas) once they reach 1,000 (e.g. 1,000 / 10,000). Sub-1000 is unchanged.
//  • Overs → cricket base-6 notation: 0, 0.1 … 0.5, 1, 1.1 … 1.5, 2 …
//    The fractional digit is BALLS (0–5), never a true decimal, and a whole
//    number of overs has NO trailing ".0" (37, not 37.0).
//  • Percentages → whole numbers (e.g. "67%").
//  • No bare "r" (runs) or "w" (wickets) suffix after a number — spell the word
//    out and space it: "580 runs @ 58.00", "3 wickets @ 12.00". Standard slash
//    notation (best figures 5/28, team scores 145/8) is KEPT — it carries no
//    r/w letters and is universal cricket shorthand.
//
// Null / undefined / blank / non-numeric → an em dash ("—"), matching the
// existing convention across the app.

export const DASH = '—'

const isNum = (v) =>
  v !== null && v !== undefined && v !== '' && !Number.isNaN(Number(v))

// ── Rates: always 2 decimals ─────────────────────────────────────────────────
// Batting/bowling averages, batting/bowling strike rates, economy & run rate.
export function fmt2(v) {
  return isNum(v) ? Number(v).toFixed(2) : DASH
}
export const fmtAverage = fmt2
export const fmtEconomy = fmt2
export const fmtStrikeRate = fmt2
export const fmtRunRate = fmt2

// ── Counts: integer with thousands separators (comma at ≥ 1,000) ──────────────
export function fmtCount(v) {
  if (!isNum(v)) return DASH
  return Math.round(Number(v)).toLocaleString('en-AU')
}
// Semantic aliases — same behaviour, clearer intent at call sites.
export const fmtRuns = fmtCount
export const fmtWickets = fmtCount
export const fmtNum = fmtCount

// ── Overs (base-6) ────────────────────────────────────────────────────────────
// Convert a stored cricket-notation overs value (10.2 = 10 overs 2 balls) → balls.
export function oversToBalls(overs) {
  if (!isNum(overs)) return 0
  const o = Number(overs)
  const whole = Math.floor(o)
  const balls = Math.round((o - whole) * 10)
  return whole * 6 + balls
}

// Convert a ball count → display string in base-6 cricket notation.
//   62 → "10.2", 60 → "10" (no trailing .0), 0 → "0".
export function ballsToOvers(balls) {
  if (balls === null || balls === undefined || Number.isNaN(Number(balls))) return DASH
  const b = Math.max(0, Math.round(Number(balls)))
  const whole = Math.floor(b / 6)
  const rem = b % 6
  return rem ? `${whole}.${rem}` : `${whole}`
}

// Format a single stored cricket-notation overs value for display. Normalises
// junk like 10.0 → "10" and a stray 36.7 (7 "balls") → "37.1".
export function fmtOvers(overs) {
  if (!isNum(overs)) return DASH
  return ballsToOvers(oversToBalls(overs))
}

// Sum an iterable of cricket-notation overs values correctly (base-6) and return
// a display string. Use this instead of adding overs as plain decimals.
export function sumOvers(values) {
  let balls = 0
  for (const v of values || []) balls += oversToBalls(v)
  return ballsToOvers(balls)
}

// ── Percentages: whole numbers ────────────────────────────────────────────────
export function fmtPct(v, { sign = false } = {}) {
  if (!isNum(v)) return DASH
  const n = Math.round(Number(v))
  return `${sign && n > 0 ? '+' : ''}${n}%`
}

// ── Spelled-out stat phrases (no bare r/w) ────────────────────────────────────
// "580 runs" / "1 run" / "580 runs @ 58.00"
export function runsPhrase(runs, avg) {
  if (!isNum(runs)) return DASH
  const word = Math.round(Number(runs)) === 1 ? 'run' : 'runs'
  const base = `${fmtCount(runs)} ${word}`
  return isNum(avg) ? `${base} @ ${fmt2(avg)}` : base
}
// "3 wickets" / "1 wicket" / "3 wickets @ 12.00"
export function wktsPhrase(wkts, avg) {
  if (!isNum(wkts)) return DASH
  const word = Math.round(Number(wkts)) === 1 ? 'wicket' : 'wickets'
  const base = `${fmtCount(wkts)} ${word}`
  return isNum(avg) ? `${base} @ ${fmt2(avg)}` : base
}
