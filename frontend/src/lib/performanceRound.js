// Reading a tracked round (routers/performance.py): each competition's stored
// pull merged into one view. Shared by the Performance Tracker page and the
// Round Review posts (social/roundReviewPost.js), so the page and a post made
// from it can never rank a round two ways.

export function pulledComps(data) {
  return ((data && data.competitions) || []).filter(c => c && c.pull && c.pull.kind === 'round')
}

export function ordinal(n) {
  if (typeof n !== 'number') return ''
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`
}

// "Swan Valley won by 19 runs": Cricket Australia's result line with the name a
// person reads out, in place of its full side name ("Swan Valley 1st XI").
export function winText(r) {
  const m = /\bwon\b(.*)$/i.exec(r.result || '')
  const winner = r.winner === 'home' ? r.home : r.winner === 'away' ? r.away : ''
  if (m && winner) return `${winner} won${m[1]}`
  return r.result || ''
}

const crestOf = (c, tid) => (tid && c.pull.crests && c.pull.crests[tid] && c.pull.crests[tid].logo) || null

// Every list tagged with its competition (`comp`, `compKey`) and crest (`logo`).
function tagged(comps, key) {
  return comps.flatMap(c => (c.pull[key] || []).map(x => ({ ...x, comp: c.name, compKey: c.key, logo: crestOf(c, x.team_id) })))
}

export const byRuns = (a, b) => b.runs - a.runs || (a.balls || 999) - (b.balls || 999)
export const byWickets = (a, b) => b.wickets - a.wickets || a.runs - b.runs

export function roundView(data) {
  const comps = pulledComps(data)
  const results = comps.flatMap(c => (c.pull.results || []).map(r => ({
    ...r, comp: c.name, compKey: c.key, homeLogo: crestOf(c, r.home_id), awayLogo: crestOf(c, r.away_id),
  })))
  const batting = tagged(comps, 'batting').sort(byRuns)
  const bowling = tagged(comps, 'bowling').sort(byWickets)
  const performers = tagged(comps, 'performers').sort((a, b) => b.points - a.points)
  const milestones = tagged(comps, 'milestones')
  const fielders = tagged(comps, 'fielders')
    .sort((a, b) => (b.catches + b.stumpings + b.run_outs) - (a.catches + a.stumpings + a.run_outs))
  const catches = tagged(comps, 'catches')
  const runOuts = tagged(comps, 'run_outs')
  const upsets = tagged(comps, 'upsets').sort((a, b) => (b.winner_rank - b.loser_rank) - (a.winner_rank - a.loser_rank))
  const margined = results.filter(r => r.margin && r.margin.closeness !== null && r.margin.closeness !== undefined)
  const closest = [...margined].sort((a, b) => a.margin.closeness - b.margin.closeness)[0] || null
  const biggest = [...results].filter(r => r.margin && r.margin.runs).sort((a, b) => b.margin.runs - a.margin.runs)[0]
    || [...results].filter(r => r.margin && r.margin.wickets).sort((a, b) => b.margin.wickets - a.margin.wickets)[0] || null
  const nextRound = comps.map(c => {
    const n = c.pull.next_round || {}
    const fixtures = (n.fixtures || []).map(f => ({ ...f, homeLogo: crestOf(c, f.home_id), awayLogo: crestOf(c, f.away_id) }))
    return { comp: c.name, compKey: c.key, round: n.round || '', fixtures, pick: typeof n.match_of_round === 'number' ? fixtures[n.match_of_round] || null : null }
  })
  const ladders = comps.map(c => ({ comp: c.name, compKey: c.key, grade: c.pull.grade, rows: c.pull.ladder || [] }))
  return {
    comps, results, batting, bowling, performers, milestones, fielders, catches, runOuts, upsets,
    closest, biggest, nextRound, ladders,
    potr: performers[0] || null, topScore: batting[0] || null, bestBowl: bowling[0] || null,
  }
}

// The whole round as plain text, for pasting into a run sheet, a newsletter or
// an email somewhere else.
export function roundText(round) {
  const v = roundView(round.data)
  const L = []
  const head = [round.round_label || 'Round', round.round_date].filter(Boolean).join(', ')
  L.push(head, '')
  L.push('AT A GLANCE')
  if (v.potr) L.push(`Player of the Round: ${v.potr.name} (${v.potr.team}) ${v.potr.line} v ${v.potr.opp}, ${v.potr.comp}`)
  if (v.topScore) L.push(`Highest score: ${v.topScore.name} (${v.topScore.team}) ${v.topScore.line} v ${v.topScore.opp}, ${v.topScore.comp}`)
  if (v.bestBowl) L.push(`Best bowling: ${v.bestBowl.name} (${v.bestBowl.team}) ${v.bestBowl.line} v ${v.bestBowl.opp}, ${v.bestBowl.comp}`)
  if (v.biggest) L.push(`Biggest win: ${winText(v.biggest)} against ${v.biggest.winner === 'home' ? v.biggest.away : v.biggest.home}, ${v.biggest.comp}`)
  if (v.closest) L.push(`Closest match: ${v.closest.home} ${v.closest.home_score} v ${v.closest.away} ${v.closest.away_score}. ${winText(v.closest)}, ${v.closest.comp}`)
  if (v.upsets.length) v.upsets.forEach(u => L.push(`Upset: ${u.winner} (${ordinal(u.winner_rank)}) beat ${u.loser} (${ordinal(u.loser_rank)}), ${u.comp}`))
  for (const c of v.comps) {
    L.push('', `${c.name.toUpperCase()} (${c.pull.grade}, ${c.pull.round})`, 'Results')
    for (const r of c.pull.results || []) {
      L.push(`  ${r.home} ${r.home_score} v ${r.away} ${r.away_score}. ${winText(r)}`)
      const lead = [...(r.top_bat || []).slice(0, 1).map(b => `${b.name} ${b.line}`), ...(r.top_bowl || []).slice(0, 1).map(b => `${b.name} ${b.line}`)]
      if (lead.length) L.push(`    ${lead.join('; ')}`)
    }
    for (const m of c.pull.not_played || []) L.push(`  ${m.home} v ${m.away}: ${m.status || 'no result'}`)
    L.push('Top batting')
    ;(c.pull.batting || []).slice(0, 5).forEach(b => L.push(`  ${b.name} (${b.team}) ${b.line} v ${b.opp}`))
    L.push('Top bowling')
    ;(c.pull.bowling || []).slice(0, 5).forEach(b => L.push(`  ${b.name} (${b.team}) ${b.line} v ${b.opp}`))
    if ((c.pull.milestones || []).length) {
      L.push('Milestones')
      c.pull.milestones.forEach(m => L.push(`  ${m.text}`))
    }
    if ((c.pull.ladder || []).length) {
      L.push('Ladder')
      c.pull.ladder.forEach(t => L.push(`  ${t.rank}. ${t.team}  ${t.won ?? 0}-${t.lost ?? 0}  ${t.points ?? 0} pts`))
    }
    const n = v.nextRound.find(x => x.compKey === c.key)
    if (n && n.fixtures.length) {
      L.push(`Next: ${n.round}`)
      n.fixtures.forEach(f => L.push(`  ${f.home} (${ordinal(f.home_rank)}) v ${f.away} (${ordinal(f.away_rank)}), ${f.label}${f.venue ? `, ${f.venue}` : ''}${n.pick === f ? '  [match of the round]' : ''}`))
    }
  }
  const notes = String((round.data && round.data.notes) || '').trim()
  if (notes) L.push('', 'NOTES', notes)
  return L.join('\n')
}
