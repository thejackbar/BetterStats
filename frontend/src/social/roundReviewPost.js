// The `review` object the Round Review layouts (round-review-templates.jsx) draw,
// built from one round saved in the Performance Tracker (routers/performance.py)
// and what the Data step typed over it.
//
// Every figure comes from the pulls stored on the round and is ranked by
// lib/performanceRound.js, the same reading the tracker page shows, so a post
// can never name a different top score from the page it was made from.
import { roundView, winText } from '../lib/performanceRound'

function splitName(name) {
  const parts = String(name || '').trim().split(/\s+/)
  if (parts.length < 2) return { first: '', last: parts[0] || '' }
  return { first: parts.slice(0, -1).join(' '), last: parts[parts.length - 1] }
}

// Every candidate for Player of the Round, best first, each with a stable key.
export function reviewPerformers(round) {
  if (!round) return []
  return roundView(round.data).performers.map(p => ({ ...p, key: `${p.compKey}:${p.match_id}:${p.name}` }))
}

// The round's headlines, one line each, in the order a wrap reads.
export function defaultHeadlines(round) {
  if (!round) return []
  const v = roundView(round.data)
  const out = []
  if (v.topScore) out.push(`${v.topScore.name} ${v.topScore.line} for ${v.topScore.team}`)
  if (v.bestBowl) out.push(`${v.bestBowl.name} ${v.bestBowl.line} for ${v.bestBowl.team}`)
  for (const m of v.milestones.filter(x => x.kind === 'hat_trick').slice(0, 1)) out.push(`Hat-trick for ${m.name} (${m.team})`)
  if (v.biggest) out.push(`${winText(v.biggest)}`)
  if (v.closest && v.closest !== v.biggest) out.push(`Thriller: ${winText(v.closest)}`)
  for (const u of v.upsets.slice(0, 1)) out.push(`Upset: ${u.winner} knock off ${u.loser}`)
  return out.slice(0, 5)
}

export function reviewPost(round, opts = {}) {
  if (!round) return {}
  const v = roundView(round.data)
  const scores = v.batting.map(b => ({
    name: b.name, team: b.team, opp: b.opp, comp: b.comp, logo: b.logo,
    figure: `${b.runs}${b.not_out ? '*' : ''}` + (b.balls ? ` (${b.balls})` : ''),
  }))
  const bowling = v.bowling.map(b => ({ name: b.name, team: b.team, opp: b.opp, comp: b.comp, logo: b.logo, figure: `${b.wickets}/${b.runs}` }))
  const perf = reviewPerformers(round)
  const chosen = perf.find(p => p.key === opts.potrKey) || perf[0] || null
  const potr = chosen ? { ...splitName(chosen.name), name: chosen.name, team: chosen.team, opp: chosen.opp, comp: chosen.comp, line: chosen.line, logo: chosen.logo, key: chosen.key } : null
  const ahead = v.nextRound.filter(n => n.pick).map(n => ({
    comp: n.comp, home: n.pick.home, away: n.pick.away, homeRank: n.pick.home_rank, awayRank: n.pick.away_rank,
    homeLogo: n.pick.homeLogo, awayLogo: n.pick.awayLogo,
    when: [n.pick.label, n.pick.time].filter(Boolean).join(' '), venue: n.pick.venue || '',
  }))
  return {
    round: round.round_label || '',
    date: '',
    comps: v.comps.map(c => c.name).join(' · '),
    title: opts.title || '',
    cta: opts.cta || '',
    headlines: Array.isArray(opts.headlines) ? opts.headlines.filter(Boolean) : defaultHeadlines(round),
    scores, bowling, potr, ahead,
    nextRound: v.nextRound.map(n => n.round).find(Boolean) || '',
  }
}
