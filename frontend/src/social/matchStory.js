// What one results row says as a sentence, for Match Cards (RR8).
//
// A finished game leads with the winner and the margin ("CROWS WIN BY 95
// RUNS"). A game in play leads with the chase when the card can answer it: the
// side batting second needs the first side's runs plus one ("JANDAKOT PARK NEED
// 220 TO WIN"), less whatever it has already made. Where the card cannot answer
// it (no batting order and both sides have a score, or a two-innings game) it
// says the game is in progress rather than guess a target.
//
// Pure, so the layout and the probe read the same rules. Nothing here reads the
// palette: `tone` names the state and the layout picks the colour.

// Runs from a score as the editor holds it: '6/188' (Australian wickets/runs),
// '188/6' typed the other way, '187' all out. The larger number is the runs.
export function scoreRuns(score) {
  const nums = String(score ?? '').match(/\d+/g)
  if (!nums) return null
  return Math.max(...nums.map(Number))
}

// '187' or '10/187' is all out; '6/188' is not; a score with no digits is no innings.
export function allOut(score) {
  const s = String(score ?? '').trim()
  if (!/\d/.test(s)) return false
  if (!s.includes('/')) return true
  const nums = s.match(/\d+/g).map(Number)
  return Math.min(...nums) >= 10
}

const hasScore = (s) => /\d/.test(String(s ?? ''))

// 'BY 95 RUNS' as the pull gives it, '95 runs' as a person might type it.
function marginWords(margin) {
  const m = String(margin || '').trim().toUpperCase()
  if (!m || m === 'IN PROGRESS') return ''
  return m.startsWith('BY ') ? m : `BY ${m}`
}

// Who batted first: what the pull read off the card, else the one side with a
// score (only the first side can have batted), else unknown.
export function firstSide(r) {
  if (r.battedFirst === 'us' || r.battedFirst === 'them') return r.battedFirst
  const u = hasScore(r.us), t = hasScore(r.them)
  if (u && !t) return 'us'
  if (t && !u) return 'them'
  return null
}

// tone: 'win' | 'loss' | 'live' | 'none'. A workspace row (`neutral`) belongs to
// neither side, so it never reads as a win or a loss: the winner is named in the
// headline and the tone is 'none'.
export function matchStory(r, names) {
  const live = r.outcome === 'LIVE'
  const neutral = !!r.neutral
  const name = { us: names.us, them: names.them }
  const score = { us: r.us, them: r.them }
  const overs = { us: r.usOvers || '', them: r.themOvers || '' }
  const first = firstSide(r)
  const order = first === 'them' ? ['them', 'us'] : ['us', 'them']
  const innings = order
    .filter((side) => hasScore(score[side]))
    .map((side) => ({ side, name: name[side], score: String(score[side]).trim(), overs: String(overs[side]).trim() }))

  let headline
  let tone
  let tag = null
  if (live) {
    tone = 'live'
    tag = 'LIVE'
    const second = first === 'us' ? 'them' : first === 'them' ? 'us' : null
    if (!first || !second) {
      headline = 'MATCH IN PROGRESS'
    } else if (!hasScore(score[second])) {
      // The chase has not started. A side still batting first has no target yet.
      headline = allOut(score[first])
        ? `${name[second]} NEED ${scoreRuns(score[first]) + 1} TO WIN`
        : `${name[first]} BAT FIRST`
    } else {
      const need = scoreRuns(score[first]) + 1 - scoreRuns(score[second])
      headline = need > 0 ? `${name[second]} NEED ${need} TO WIN` : 'MATCH IN PROGRESS'
    }
  } else if (r.outcome === 'W' || r.outcome === 'L') {
    const winner = r.outcome === 'W' ? 'us' : 'them'
    headline = `${name[winner]} WIN ${marginWords(r.margin)}`.trim()
    tone = neutral ? 'none' : r.outcome === 'W' ? 'win' : 'loss'
    tag = neutral ? null : r.outcome === 'W' ? 'WIN' : 'LOSS'
  } else {
    // A tie, a draw, an abandoned game: the pull cannot say which, so the card
    // says only that nobody won. The club can reword it (Brand, this layout).
    headline = names.noWinner || 'NO WINNER'
    tone = 'none'
  }
  return { headline, tone, tag, innings, live }
}
