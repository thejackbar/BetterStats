// Recombine a subset of a player's per-season rollups (backend/app/services/
// iq_scout.py's _rollup, one entry per year) into a single summary for an
// arbitrary look-back window — entirely client-side, so switching "last N
// seasons" is instant with no second network round trip.
//
// Plain counts (matches, runs, wickets, …) just sum. Rates (average, strike
// rate, bowling average, economy) are re-derived from the SUMMED raw counts,
// never averaged from the per-season rates — same rule _rollup() itself
// follows. best/high_score are formatted strings, combined by parsing +
// comparing (mirrors iq_opponent._best_figures's tie-break: more wickets
// wins, fewer runs breaks a tie).

export const WINDOW_OPTIONS = [
  { n: 1, label: 'Last 1 season' },
  { n: 2, label: 'Last 2 seasons' },
  { n: 5, label: 'Last 5 seasons' },
  { n: null, label: 'Full window' },
]

function parseBest(best) {
  // "5/24" -> [5, 24]. No wickets recorded that season -> null.
  if (!best) return null
  const m = /^(\d+)\/(\d+)$/.exec(best)
  return m ? [parseInt(m[1], 10), parseInt(m[2], 10)] : null
}

function bestOf(seasons) {
  let best = null
  for (const s of seasons) {
    const bp = parseBest(s.best)
    if (!bp) continue
    if (!best || bp[0] > best[0] || (bp[0] === best[0] && bp[1] < best[1])) best = bp
  }
  return best ? `${best[0]}/${best[1]}` : null
}

function highScoreOf(seasons) {
  let best = null // { value, notOut }
  for (const s of seasons) {
    if (s.high_score == null) continue
    const notOut = String(s.high_score).endsWith('*')
    const value = parseInt(s.high_score, 10)
    if (isNaN(value)) continue
    if (!best || value > best.value) best = { value, notOut }
  }
  return best ? `${best.value}${best.notOut ? '*' : ''}` : null
}

const sum = (seasons, key) => seasons.reduce((acc, s) => acc + (s[key] || 0), 0)

export function rollupSeasons(seasons) {
  if (!seasons || seasons.length === 0) {
    return {
      matches: 0, innings: 0, runs: 0, not_outs: 0, balls_faced: 0,
      average: null, strike_rate: null, high_score: null,
      fifties: 0, hundreds: 0, ducks: 0,
      wickets: 0, bowling_balls: 0, runs_conceded: 0, maidens: 0, five_fors: 0,
      bowling_average: null, economy: null, best: null,
      catches: 0, catches_wk: 0, stumpings: 0, run_outs: 0,
    }
  }
  const matches = sum(seasons, 'matches')
  const innings = sum(seasons, 'innings')
  const runs = sum(seasons, 'runs')
  const notOuts = sum(seasons, 'not_outs')
  const ballsFaced = sum(seasons, 'balls_faced')
  const wickets = sum(seasons, 'wickets')
  const bowlingBalls = sum(seasons, 'bowling_balls')
  const runsConceded = sum(seasons, 'runs_conceded')
  const outs = Math.max(innings - notOuts, 0)

  return {
    matches, innings, runs, not_outs: notOuts, balls_faced: ballsFaced,
    average: outs ? Math.round((runs / outs) * 100) / 100 : null,
    strike_rate: ballsFaced ? Math.round((100 * runs / ballsFaced) * 100) / 100 : null,
    high_score: highScoreOf(seasons),
    fifties: sum(seasons, 'fifties'),
    hundreds: sum(seasons, 'hundreds'),
    ducks: sum(seasons, 'ducks'),
    wickets, bowling_balls: bowlingBalls, runs_conceded: runsConceded,
    maidens: sum(seasons, 'maidens'),
    five_fors: sum(seasons, 'five_fors'),
    bowling_average: wickets ? Math.round((runsConceded / wickets) * 100) / 100 : null,
    economy: bowlingBalls ? Math.round((runsConceded / (bowlingBalls / 6)) * 100) / 100 : null,
    best: bestOf(seasons),
    catches: sum(seasons, 'catches'),
    catches_wk: sum(seasons, 'catches_wk'),
    stumpings: sum(seasons, 'stumpings'),
    run_outs: sum(seasons, 'run_outs'),
  }
}
