// Reading a tracked round (routers/performance.py): each competition's stored
// pull merged into one view. Shared by the Performance Tracker page and the
// Round Review posts (social/roundReviewPost.js), so the page and a post made
// from it can never rank a round two ways.

// `keys` (optional) is the grades picked in the page's or a post's filter; null
// or empty is every grade.
export function pulledComps(data, keys) {
  const on = keys && keys.length ? new Set(keys) : null
  return ((data && data.competitions) || []).filter(c => c && c.pull && c.pull.kind === 'round' && (!on || on.has(c.key)))
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

// A club name reduced to what tells it apart: "Applecross Cricket Club" and
// the side "Applecross" both read "applecross".
export function normClub(s) {
  return String(s || '').toLowerCase()
    .replace(/\b(district\s+)?cricket\s+(club|association)\b|\bc\.?c\.?(?=\s|$)|\binc\.?(?=\s|$)/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ').trim()
}

// The crest for a side, read from the workspace's crest library as it is NOW
// (GET /admin/social/crests), so a crest changed after the pull (white edge,
// uploaded) still reaches the page and the posts:
//   1. the side's club id (`pull.clubs`, pulls from v9.149.1) in the library;
//   2. the crest address the pull stored (`pull.crests`);
//   3. the library entry whose club name the side's name starts with, longest
//      first: a pull read before crests were stored has only the name.
//   (`data`, optional) the round's own pulls back up a club named outside a pull
//   (a season or career row) that the library does not hold yet.
export function crestLookup(library, data) {
  const byId = new Map()
  const byName = []
  const pulledId = new Map()
  const pulledName = []
  for (const c of pulledComps(data)) {
    for (const [tid, club] of Object.entries(c.pull.clubs || {})) {
      const logo = c.pull.crests && c.pull.crests[tid] && c.pull.crests[tid].logo
      if (!logo || !club) continue
      if (club.id) pulledId.set(String(club.id).toLowerCase(), logo)
      const n = normClub(club.name)
      if (n) pulledName.push([n, logo])
    }
  }
  for (const c of library || []) {
    if (!c || !c.logo) continue
    if (c.caOrgId) byId.set(String(c.caOrgId).toLowerCase(), c.logo)
    const n = normClub(c.name)
    if (n) byName.push([n, c.logo])
  }
  byName.sort((a, b) => b[0].length - a[0].length)
  const lookup = (pull, tid, teamName) => {
    const club = tid && pull.clubs ? pull.clubs[tid] : null
    if (club && club.id && byId.has(String(club.id).toLowerCase())) return byId.get(String(club.id).toLowerCase())
    const stored = tid && pull.crests && pull.crests[tid] && pull.crests[tid].logo
    if (stored) return stored
    const t = normClub((club && club.name) || teamName)
    if (t) for (const [n, logo] of byName) if (t === n || t.startsWith(`${n} `)) return logo
    return null
  }
  // A club named outside a pull (a season or career row): its id, else its name.
  lookup.club = (clubId, name) => {
    const id = clubId ? String(clubId).toLowerCase() : ''
    if (id && byId.has(id)) return byId.get(id)
    const t = normClub(name)
    if (t) for (const [n, logo] of byName) if (t === n || t.startsWith(`${n} `)) return logo
    if (id && pulledId.has(id)) return pulledId.get(id)
    if (t) for (const [n, logo] of pulledName) if (t === n || t.startsWith(`${n} `)) return logo
    return null
  }
  return lookup
}

// Every list tagged with its competition (`comp`, `compKey`) and crest (`logo`).
function tagged(comps, key, crest) {
  return comps.flatMap(c => (c.pull[key] || []).map(x => ({ ...x, comp: c.name, compKey: c.key, logo: crest(c.pull, x.team_id, x.team) })))
}

export const byRuns = (a, b) => b.runs - a.runs || (a.balls || 999) - (b.balls || 999)
export const byWickets = (a, b) => b.wickets - a.wickets || a.runs - b.runs

// `library` is the workspace crest library (GET /admin/social/crests); without it
// a side shows the crest its pull stored, if any.
export function roundView(data, library, keys) {
  const crest = crestLookup(library)
  const comps = pulledComps(data, keys)
  const results = comps.flatMap(c => (c.pull.results || []).map(r => ({
    ...r, comp: c.name, compKey: c.key, homeLogo: crest(c.pull, r.home_id, r.home), awayLogo: crest(c.pull, r.away_id, r.away),
  })))
  const batting = tagged(comps, 'batting', crest).sort(byRuns)
  const bowling = tagged(comps, 'bowling', crest).sort(byWickets)
  const performers = tagged(comps, 'performers', crest).sort((a, b) => b.points - a.points)
  const milestones = tagged(comps, 'milestones', crest)
  const fielders = tagged(comps, 'fielders', crest)
    .sort((a, b) => (b.catches + b.stumpings + b.run_outs) - (a.catches + a.stumpings + a.run_outs))
  const catches = tagged(comps, 'catches', crest)
  const runOuts = tagged(comps, 'run_outs', crest)
  const upsets = tagged(comps, 'upsets', crest).sort((a, b) => (b.winner_rank - b.loser_rank) - (a.winner_rank - a.loser_rank))
  const margined = results.filter(r => r.margin && r.margin.closeness !== null && r.margin.closeness !== undefined)
  const closest = [...margined].sort((a, b) => a.margin.closeness - b.margin.closeness)[0] || null
  const biggest = [...results].filter(r => r.margin && r.margin.runs).sort((a, b) => b.margin.runs - a.margin.runs)[0]
    || [...results].filter(r => r.margin && r.margin.wickets).sort((a, b) => b.margin.wickets - a.margin.wickets)[0] || null
  const nextRound = comps.map(c => {
    const n = c.pull.next_round || {}
    // A side with no opponent has the bye: name it rather than leave a blank.
    const fixtures = (n.fixtures || []).map(f => ({
      ...f, home: f.home || 'Bye', away: f.away || 'Bye', bye: !f.home || !f.away,
      homeLogo: f.home ? crest(c.pull, f.home_id, f.home) : null, awayLogo: f.away ? crest(c.pull, f.away_id, f.away) : null,
    }))
    return { comp: c.name, compKey: c.key, round: n.round || '', fixtures, pick: typeof n.match_of_round === 'number' ? fixtures[n.match_of_round] || null : null }
  })
  const ladders = comps.map(c => ({
    comp: c.name, compKey: c.key, grade: c.pull.grade,
    rows: (c.pull.ladder || []).map(r => ({ ...r, logo: crest(c.pull, r.team_id, r.team) })),
  }))
  return {
    comps, results, batting, bowling, performers, milestones, fielders, catches, runOuts, upsets,
    closest, biggest, nextRound, ladders,
    potr: performers[0] || null, topScore: batting[0] || null, bestBowl: bowling[0] || null,
  }
}

// The five season tables, in the order the page, the text and the posts show them.
export const LEADER_TABLES = [
  ['Most runs', 'runs'], ['Most wickets', 'wickets'], ['Most catches', 'catches'],
  ['Highest score', 'high_score'], ['Best bowling', 'best_bowling'],
]

// ── Season leaderboards, for any set of grades ──────────────────────────────

const LEADERS = 10
const addKeys = ['matches', 'inns', 'runs', 'not_outs', 'fifties', 'hundreds', 'wickets', 'bowl_runs', 'five_fors', 'catches', 'stumpings', 'run_outs']

// Season blocks (GET .../season `competitions`) for the picked grades.
export function seasonBlocks(season, keys) {
  if (!season || !Array.isArray(season.competitions)) return []
  const on = keys && keys.length ? new Set(keys) : null
  return season.competitions.filter(b => !b.error && (!on || on.has(b.key)))
}

// One leaderboard set over the picked grades: a player in two grades counts
// both, their bests are the better of the two. Ranked the same way as the
// server's own (services/performance_season.leaderboards).
export function seasonBoards(season, keys, library, data) {
  const blocks = seasonBlocks(season, keys)
  const crest = crestLookup(library, data)
  const by = new Map()
  for (const b of blocks) {
    for (const p of b.players || []) {
      const held = by.get(p.pid)
      if (!held) { by.set(p.pid, { ...p, comps: [b.name] }); continue }
      for (const k of addKeys) held[k] = (held[k] || 0) + (p[k] || 0)
      if ((p.hs || 0) > (held.hs || 0) || (p.hs === held.hs && p.hs_not_out && !held.hs_not_out)) { held.hs = p.hs; held.hs_not_out = p.hs_not_out }
      if (p.best && (!held.best || p.best[0] > held.best[0] || (p.best[0] === held.best[0] && p.best[1] < held.best[1]))) held.best = p.best
      held.comps.push(b.name)
    }
  }
  const all = [...by.values()].map(p => ({ ...p, logo: crest.club(p.club_id, p.club) }))
  const row = (p, value, sub = '') => ({ pid: p.pid, name: p.name, club: p.club, club_id: p.club_id, logo: p.logo, value, sub, comps: p.comps })
  const bat = all.filter(p => p.runs || p.inns)
  const bowl = all.filter(p => p.wickets)
  const avg = (r, d) => (d > 0 ? (r / d).toFixed(1) : '')
  return {
    runs: [...bat].sort((a, b) => b.runs - a.runs || a.inns - b.inns || a.name.localeCompare(b.name)).slice(0, LEADERS)
      .map(p => row(p, p.runs, `${p.inns} inns${avg(p.runs, p.inns - p.not_outs) ? `, avg ${avg(p.runs, p.inns - p.not_outs)}` : ''}`)),
    wickets: [...bowl].sort((a, b) => b.wickets - a.wickets || a.bowl_runs - b.bowl_runs || a.name.localeCompare(b.name)).slice(0, LEADERS)
      .map(p => row(p, p.wickets, `avg ${avg(p.bowl_runs, p.wickets)}`)),
    catches: all.filter(p => p.catches).sort((a, b) => b.catches - a.catches || a.name.localeCompare(b.name)).slice(0, LEADERS)
      .map(p => row(p, p.catches, p.stumpings ? `${p.stumpings} st` : '')),
    high_score: bat.filter(p => p.hs).sort((a, b) => b.hs - a.hs || (b.hs_not_out ? 1 : 0) - (a.hs_not_out ? 1 : 0) || a.name.localeCompare(b.name)).slice(0, LEADERS)
      .map(p => row(p, `${p.hs}${p.hs_not_out ? '*' : ''}`)),
    best_bowling: bowl.filter(p => p.best).sort((a, b) => b.best[0] - a.best[0] || a.best[1] - b.best[1] || a.name.localeCompare(b.name)).slice(0, LEADERS)
      .map(p => row(p, `${p.best[0]}/${p.best[1]}`)),
  }
}

// ── Milestones, in one shape ─────────────────────────────────────────────────
// scope: match (this round's scorecards), season, career. stat: batting,
// bowling, fielding, games. `title` is the mark, `detail` the figure behind it.

const MATCH_TITLES = {
  hundred: ['batting', 'Hundred'], fifty: ['batting', 'Fifty'], five_for: ['bowling', 'Five wickets'],
  hat_trick: ['bowling', 'Hat-trick'], fielding: ['fielding', 'Four or more dismissals'],
}
const STAT_OF = { runs: 'batting', wickets: 'bowling', catches: 'fielding', matches: 'games' }

export function milestoneRows(data, season, keys, library) {
  const crest = crestLookup(library, data)
  const out = []
  for (const c of pulledComps(data, keys)) {
    for (const m of c.pull.milestones || []) {
      const [stat, title] = MATCH_TITLES[m.kind] || ['batting', 'Milestone']
      const detail = String(m.text || '').replace(/^.*?\)\s+(made|took|had a hand in)\s+/, '').replace(/\s+against\s+/, ' v ')
      out.push({ scope: 'match', stat, title, detail, name: m.name, club: m.team, comp: c.name, compKey: c.key, logo: crest(c.pull, m.team_id, m.team), rank: m.kind === 'hundred' || m.kind === 'hat_trick' ? 1 : m.kind === 'five_for' ? 2 : 4, mark: 0 })
    }
  }
  for (const b of seasonBlocks(season, keys)) {
    for (const m of [...(b.season_milestones || []), ...(b.career_milestones || [])]) {
      const scope = m.scope || (String(m.kind).startsWith('career') ? 'career' : 'season')
      const key = m.stat || String(m.kind).split('_').pop()
      const word = { runs: 'runs', wickets: 'wickets', catches: 'catches', matches: 'games' }[key] || key
      const title = scope === 'career' ? (key === 'matches' ? `${m.mark} games` : `${Number(m.mark).toLocaleString('en-AU')} career ${word}`) : `${m.mark} season ${word}`
      const detail = m.value !== undefined ? (scope === 'career' ? `${Number(m.value).toLocaleString('en-AU')} for ${m.club}` : `${m.value} so far`) : m.text
      out.push({ scope, stat: STAT_OF[key] || 'batting', title, detail, name: m.name, club: m.club, comp: b.name, compKey: b.key, logo: crest.club(m.club_id, m.club), rank: scope === 'career' ? 0 : 3, mark: Number(m.mark) || 0 })
    }
  }
  // Career marks first, then hundreds and hat-tricks, five-fors, season marks
  // (biggest first), then fifties and fielding.
  return out.sort((a, b) => a.rank - b.rank || b.mark - a.mark || a.name.localeCompare(b.name))
}

// ── The whole round as plain text ────────────────────────────────────────────
// For pasting into a run sheet, a newsletter or an email somewhere else.
// `season` is GET /admin/performance/rounds/{id}/season, when it has been read;
// `keys` is the grades picked on the page.
export function roundText(round, season, keys) {
  const v = roundView(round.data, null, keys)
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
  if (season && seasonBlocks(season, keys).length) {
    const lead = (title, board) => {
      L.push('', title)
      for (const [label, key] of LEADER_TABLES) {
        const rows = (board[key] || []).slice(0, 5)
        if (rows.length) L.push(`${label}: ${rows.map(r => `${r.name} (${r.club}) ${r.value}`).join('; ')}`)
      }
    }
    const blocks = seasonBlocks(season, keys)
    if (blocks.length > 1) lead('SEASON LEADERS, ALL PICKED GRADES', seasonBoards(season, keys, null, round.data))
    for (const b of blocks) lead(`SEASON LEADERS, ${String(b.name).toUpperCase()}`, seasonBoards(season, [b.key], null, round.data))
    const ms = milestoneRows({ competitions: [] }, season, keys).filter(m => m.scope !== 'match')
    if (ms.length) {
      L.push('', 'SEASON AND CAREER MILESTONES')
      ms.forEach(m => L.push(`  ${m.name} (${m.club}): ${m.title}, ${m.detail}. ${m.comp}`))
    }
  }
  const notes = String((round.data && round.data.notes) || '').trim()
  if (notes) L.push('', 'NOTES', notes)
  return L.join('\n')
}
