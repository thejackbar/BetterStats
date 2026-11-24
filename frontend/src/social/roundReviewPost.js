// The `review` object the Round Review layouts (round-review-templates.jsx) draw,
// built from one round saved in the Performance Tracker (routers/performance.py)
// and what the Data step typed over it.
//
// Every figure comes from the pulls stored on the round and is ranked by
// lib/performanceRound.js, the same reading the tracker page shows, so a post
// can never name a different top score from the page it was made from.
import { roundView, winText, seasonBoards, milestoneRows, LEADER_TABLES, ordinal } from '../lib/performanceRound'

function splitName(name) {
  const parts = String(name || '').trim().split(/\s+/)
  if (parts.length < 2) return { first: '', last: parts[0] || '' }
  return { first: parts.slice(0, -1).join(' '), last: parts[parts.length - 1] }
}

// Every candidate for Player of the Round, best first, each with a stable key.
export function reviewPerformers(round, library, keys) {
  if (!round) return []
  return roundView(round.data, library, keys).performers.map(p => ({ ...p, key: `${p.compKey}:${p.match_id}:${p.name}` }))
}

// The round's headlines, one line each, in the order a wrap reads.
export function defaultHeadlines(round, keys) {
  if (!round) return []
  const v = roundView(round.data, null, keys)
  const out = []
  if (v.topScore) out.push(`${v.topScore.name} ${v.topScore.line} for ${v.topScore.team}`)
  if (v.bestBowl) out.push(`${v.bestBowl.name} ${v.bestBowl.line} for ${v.bestBowl.team}`)
  for (const m of v.milestones.filter(x => x.kind === 'hat_trick').slice(0, 1)) out.push(`Hat-trick for ${m.name} (${m.team})`)
  if (v.biggest) out.push(`${winText(v.biggest)}`)
  if (v.closest && v.closest !== v.biggest) out.push(`Thriller: ${winText(v.closest)}`)
  for (const u of v.upsets.slice(0, 1)) out.push(`Upset: ${u.winner} knock off ${u.loser}`)
  return out.slice(0, 5)
}

// `library` is the workspace crest library, read live so the posts show the
// crests as they are now (see lib/performanceRound.crestLookup).
// `season` is GET /admin/performance/rounds/{id}/season (leaderboards and
// season and career milestones); `opts.grades` the grades picked, none for all.
export function reviewPost(round, opts = {}, library, season) {
  if (!round) return {}
  const keys = opts.grades && opts.grades.length ? opts.grades : null
  const v = roundView(round.data, library, keys)
  const scores = v.batting.map(b => ({
    name: b.name, team: b.team, opp: b.opp, comp: b.comp, logo: b.logo,
    figure: `${b.runs}${b.not_out ? '*' : ''}` + (b.balls ? ` (${b.balls})` : ''),
  }))
  const bowling = v.bowling.map(b => ({ name: b.name, team: b.team, opp: b.opp, comp: b.comp, logo: b.logo, figure: `${b.wickets}/${b.runs}` }))
  const perf = reviewPerformers(round, library, keys)
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
    headlines: Array.isArray(opts.headlines) ? opts.headlines.filter(Boolean) : defaultHeadlines(round, keys),
    scores, bowling, potr, ahead,
    results: v.results.map(r => ({
      comp: r.comp, home: r.home, away: r.away, homeScore: r.home_score, awayScore: r.away_score,
      homeLogo: r.homeLogo, awayLogo: r.awayLogo, winner: r.winner, margin: winText(r),
    })),
    board: (() => {
      const key = opts.board && LEADER_TABLES.some(([, k]) => k === opts.board) ? opts.board : 'runs'
      const label = (LEADER_TABLES.find(([, k]) => k === key) || ['Most runs'])[0]
      const rows = season ? (seasonBoards(season, keys, library, round.data)[key] || []) : []
      return { key, label, rows: rows.map(r => ({ name: r.name, club: r.club, logo: r.logo, value: String(r.value), sub: r.sub })) }
    })(),
    milestones: milestoneRows(round.data, season, keys, library)
      .filter(m => (!opts.scopes || opts.scopes.includes(m.scope)) && (!opts.stats || opts.stats.includes(m.stat))),
    ladder: (() => {
      const l = v.ladders.filter(x => x.rows.length)
      const one = l.find(x => x.compKey === opts.ladder) || l[0]
      return one ? { comp: one.comp, rows: one.rows.map(r => ({ rank: r.rank, team: r.team, logo: r.logo, played: r.played, won: r.won, lost: r.lost, points: r.points })) } : null
    })(),
    fixtures: v.nextRound.flatMap(n => n.fixtures.map(f => ({
      comp: n.comp, home: f.home, away: f.away, homeLogo: f.homeLogo, awayLogo: f.awayLogo,
      homeRank: ordinal(f.home_rank), awayRank: ordinal(f.away_rank),
      when: [f.label, f.time].filter(Boolean).join(' '), venue: f.venue || '', pick: n.pick === f, bye: !!f.bye,
    }))),
    nextRound: v.nextRound.map(n => n.round).find(Boolean) || '',
  }
}
