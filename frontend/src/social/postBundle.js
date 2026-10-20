// What the editor holds for one post type, shaped the way a template's words read it
// (see postFields.js for the words). The editor already keeps all of this in its own
// state, in the shapes the built-in layouts want; this is the one place that turns it
// into the flat bundle (data.post) a bound text field or photo area resolves against.
//
// A group is left out entirely while the club has typed nothing into it, so the template
// still shows its sample words rather than a screen of blanks. Once anything is held, a
// value that is missing prints nothing.

const text = (v) => (v === undefined || v === null ? '' : String(v))
const full = (first, last) => [first, last].filter(Boolean).join(' ')
// A group, or undefined when every value in it is empty.
const held = (group) => (Object.values(group).some((v) => text(v).trim() !== '') ? group : undefined)

const OUTCOME_WORD = { W: 'WIN', L: 'LOSS', D: 'DRAW', T: 'TIE', TIE: 'TIE' }

export function fixtureRows(fixtures) {
  return (fixtures || []).map((f) => ({
    grade: text(f.grade), opponent: text(f.opp), short: text(f.oppMono),
    homeaway: f.ha === 'H' ? 'HOME' : f.ha === 'A' ? 'AWAY' : text(f.ha),
    time: text(f.time), venue: text(f.venue),
  }))
}

export function resultRows(results) {
  return (results || []).map((r) => {
    const o = text(r.outcome).toUpperCase()
    return {
      grade: text(r.grade), opponent: text(r.opp), short: text(r.oppMono), us: text(r.us), them: text(r.them),
      outcome: OUTCOME_WORD[o] || o, margin: text(r.margin),
    }
  })
}

// The Final Score tab. `winnerName` is the side that won, '' for a tie.
export function finalBundle(result, { teamName = '', oppName = '' } = {}) {
  const r = result || {}
  const side = r.winner === 'OPPONENT' ? 'them' : r.winner === 'TIE' ? 'tie' : 'us'
  const perfNames = ['team', 'opponent'].map((k) => [...((r.topBatters || {})[k] || []), ...((r.topBowlers || {})[k] || [])].map((p) => text(p.last) + text(p.line)).join('')).join('')
  const typed = held({
    us: r.teamScore, them: r.oppScore, usOvers: r.teamOvers, themOvers: r.oppOvers, margin: r.margin, grade: r.grade,
    potm: full(r.motmFirst, r.motmLast), perf: perfNames,
  })
  const rows = (arr) => (arr || []).map((p) => ({ name: text(p.last), line: text(p.line) })).filter((p) => p.name || p.line)
  const potmBat = text(r.motmBat), potmBowl = text(r.motmBowl)
  const out = {}
  if (typed) {
    out.final = {
      us: text(r.teamScore), them: text(r.oppScore), usOvers: text(r.teamOvers), themOvers: text(r.oppOvers),
      result: side === 'tie' ? 'TIE' : side === 'us' ? 'WIN' : 'LOSS', margin: text(r.margin),
      winner: side === 'tie' ? '' : side === 'us' ? teamName : oppName, grade: text(r.grade),
    }
    const potm = held({ first: r.motmFirst, last: r.motmLast, role: r.motmRole, bat: potmBat, bowl: potmBowl })
    if (potm) {
      out.potm = {
        name: full(r.motmFirst, r.motmLast), first: text(r.motmFirst), last: text(r.motmLast), role: text(r.motmRole),
        bat: potmBat, bowl: potmBowl, line: [potmBat, potmBowl].filter(Boolean).join(' · '), summary: '',
      }
    }
    out.perf = {
      us: { bat: rows(r.topBatters && r.topBatters.team), bowl: rows(r.topBowlers && r.topBowlers.team) },
      them: { bat: rows(r.topBatters && r.topBatters.opponent), bowl: rows(r.topBowlers && r.topBowlers.opponent) },
    }
  }
  return out
}

// The Player of the Match tab. `player` is the editor's template player (or undefined), `photo` the picture to show.
export function motmBundle(motm, player, photo) {
  const m = motm || {}
  const stats = (m.stats || []).filter((s) => s.label && s.value).map((s) => ({ label: text(s.label), value: text(s.value) }))
  const out = {}
  if (player || m.summary) {
    const first = text(player && player.first), last = text(player && player.last)
    out.potm = {
      name: full(first, last), first, last, role: text(player && (player.roleLong || player.role)),
      bat: '', bowl: '', line: stats.map((s) => `${s.value} ${s.label}`).join(' · '), summary: text(m.summary), photo: player ? text(photo) : null,
    }
  }
  if (stats.length) out.stats = stats
  return out
}

export function announceBundle(announcement, player, photo) {
  const a = announcement || {}
  const first = text(player && player.first), last = text(player && player.last)
  return {
    announce: {
      kind: text(a.kind), headline: text(a.headline), subheadline: text(a.subheadline),
      name: full(first, last), first, last, photo: player ? text(photo) : null,
    },
  }
}

export function tossBundle(toss, { teamName = '', oppName = '' } = {}) {
  const t = toss || {}
  const winner = t.winner === 'OPPONENT' ? oppName : teamName
  const decision = text(t.decision || 'BAT').toUpperCase()
  return { toss: { text: `${winner} WON THE TOSS`, winner: text(winner), decision } }
}

// Team of the week: one row per player on the post, in post order.
export function totwBundle(players, heading) {
  return {
    totw: (players || []).map((p) => ({
      name: full(p.first, p.last), first: text(p.first), last: text(p.last), photo: text(p.headshot),
      line: text(p.totw && p.totw.line), grade: text(p.totw && p.totw.grade), opponent: text(p.totw && p.totw.opp),
      points: text(p.totw && p.totw.points),
    })),
    tw: { heading: text(heading) },
  }
}

// Milestones: the cards the post prints (the editor's own card shape, in post order).
export function milestoneBundle(cards, title) {
  return {
    milestones: (cards || []).map((c) => ({
      name: full(c.first, c.last), first: text(c.first), last: text(c.last), value: text(c.value), unit: text(c.unit),
      date: text(c.dateLabel), photo: text(c.headshot),
    })),
    ms: { title: text(title) },
  }
}

// An event poster, and the dated list some of the event layouts carry (the items already prepared for printing).
export function eventBundle(event, list, photo) {
  const e = event || {}
  return {
    event: {
      kicker: text(e.kicker), title: text(e.title), subtitle: text(e.subtitle), date: text(e.date), time: text(e.time),
      venue: text(e.venue), price: text(e.price), cta: text(e.cta), sponsor: text(e.sponsor), photo: photo ? text(photo) : null,
    },
    items: ((list && list.items) || []).map((it) => ({
      title: text(it.title), date: text(it.dateLabel), day: text(it.day), month: text(it.mon), time: text(it.time),
      venue: text(it.venue), price: text(it.price),
    })),
  }
}
