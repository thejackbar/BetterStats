// The words a template can use on every post type other than the line up (which has
// its own rules in boundResolve.js). A word in a design, such as {{fixture 2 venue}},
// becomes a "bind" the post fills in from what the editor holds for that type.
//
// A bind is a short dotted path:
//   fixture.2.venue      row 2 of the fixtures list, its venue
//   final.us             the Final Score tab's own score
//   potm.photo           the player of the match's photo
//
// The Canva app keeps its own copy of this table (canva-app/src/template/postFields.ts)
// and both are tested against canva-app/src/template/token-cases.json, so they cannot drift.
//
// What each post type has to show, and which tab it belongs to:
//   fixtures      fixture N ...                 (one row per grade playing)
//   results       result N ...                  (one row per grade that played)
//   result        our score, opponent score, result, margin, potm ..., our batter N ...
//   motm          potm ..., stat N ...
//   totw          totw N ...
//   milestones    milestone N ..., milestone title
//   announcement  announcement headline | subheadline | kind | name | first | last | photo
//   toss          toss winner | decision | (toss)
//   events        event title | kicker | ..., event item N ...

export const POST_TYPES = ['lineup', 'fixtures', 'results', 'result', 'motm', 'totw', 'milestones', 'announcement', 'toss', 'events']

const norm = (s) => String(s || '').toLowerCase().replace(/[{}]/g, '').replace(/\s+/g, ' ').trim()

// Rows: `<word> N <field>`. `group` is the first part of the bind; `rows` is where the editor
// keeps them (data.post[rows]).
export const LISTS = {
  fixture: {
    group: 'fixture', rows: 'fixtures', max: 8, fallback: 'opponent',
    fields: { opponent: 'opponent', opp: 'opponent', grade: 'grade', team: 'grade', short: 'short', monogram: 'short', 'home away': 'homeaway', homeaway: 'homeaway', ha: 'homeaway', time: 'time', venue: 'venue' },
  },
  result: {
    group: 'result', rows: 'results', max: 8, fallback: 'opponent',
    fields: { opponent: 'opponent', opp: 'opponent', grade: 'grade', team: 'grade', short: 'short', monogram: 'short', us: 'us', 'our score': 'us', score: 'us', them: 'them', 'their score': 'them', 'opponent score': 'them', outcome: 'outcome', result: 'outcome', margin: 'margin' },
  },
  milestone: {
    group: 'milestone', rows: 'milestones', max: 8, fallback: 'name',
    fields: { name: 'name', first: 'first', last: 'last', photo: 'photo', headshot: 'photo', value: 'value', number: 'value', unit: 'unit', date: 'date' },
  },
  totw: {
    group: 'totw', rows: 'totw', max: 15, fallback: 'name',
    fields: { name: 'name', first: 'first', last: 'last', photo: 'photo', headshot: 'photo', line: 'line', performance: 'line', grade: 'grade', opponent: 'opponent', opp: 'opponent', points: 'points' },
  },
  stat: {
    group: 'stat', rows: 'stats', max: 6, fallback: 'value',
    fields: { label: 'label', value: 'value' },
  },
  'event item': {
    group: 'item', rows: 'items', max: 8, fallback: 'title',
    fields: { title: 'title', date: 'date', day: 'day', month: 'month', time: 'time', venue: 'venue', price: 'price' },
  },
}

// Words on their own. Each one means the same on every post type, but only the type it
// belongs to holds a value for it (the others show the sample until it does).
export const SINGLES = {
  'our score': 'final.us', 'opponent score': 'final.them', 'their score': 'final.them',
  'our overs': 'final.usOvers', 'opponent overs': 'final.themOvers', 'their overs': 'final.themOvers',
  result: 'final.result', 'final result': 'final.result', margin: 'final.margin', winner: 'final.winner', grade: 'final.grade',
  'potm name': 'potm.name', 'potm first': 'potm.first', 'potm last': 'potm.last', 'potm role': 'potm.role',
  'potm bat': 'potm.bat', 'potm bowl': 'potm.bowl', 'potm line': 'potm.line', 'potm summary': 'potm.summary', 'potm photo': 'potm.photo',
  toss: 'toss.text', 'toss text': 'toss.text', 'toss winner': 'toss.winner', 'toss decision': 'toss.decision',
  'announcement headline': 'announce.headline', 'announcement subheadline': 'announce.subheadline', 'announcement kind': 'announce.kind',
  'announcement name': 'announce.name', 'announcement first': 'announce.first', 'announcement last': 'announce.last', 'announcement photo': 'announce.photo',
  'milestone title': 'ms.title', 'totw heading': 'tw.heading',
  'event kicker': 'event.kicker', 'event title': 'event.title', 'event subtitle': 'event.subtitle', 'event date': 'event.date', 'event time': 'event.time',
  'event venue': 'event.venue', 'event price': 'event.price', 'event cta': 'event.cta', 'event sponsor': 'event.sponsor', 'event photo': 'event.photo',
}

const PERF_ALIAS = { our: 'us', opponent: 'them', their: 'them', opposition: 'them' }

// null when the words are not one of these.
export function postBindFromToken(token) {
  const t = norm(token)
  if (SINGLES[t]) return SINGLES[t]
  for (const [word, def] of Object.entries(LISTS)) {
    if (!t.startsWith(word)) continue
    const m = t.slice(word.length).match(/^ ?(\d{1,2})(?: (.+))?$/)
    if (!m) continue
    const n = Number(m[1])
    if (n < 1 || n > def.max) return null
    const field = m[2] === undefined ? def.fallback : def.fields[m[2]]
    return field ? `${def.group}.${n}.${field}` : null
  }
  // our batter 2 name | opponent bowler 1 line
  const p = t.match(/^(our|opponent|their|opposition) (batter|bowler) ?(\d) ?(name|line)?$/)
  if (p) {
    const n = Number(p[3])
    return n >= 1 && n <= 3 ? `perf.${PERF_ALIAS[p[1]]}.${p[2] === 'batter' ? 'bat' : 'bowl'}.${n}.${p[4] || 'name'}` : null
  }
  return null
}

const FIELD_WORD = {
  opponent: '', grade: ' (grade)', short: ' (short name)', homeaway: ' (home or away)', time: ' (time)', venue: ' (venue)',
  us: ' (our score)', them: ' (their score)', outcome: ' (result)', margin: ' (margin)', name: '', first: ' (first name)', last: ' (last name)',
  photo: ' (photo)', value: '', unit: ' (unit)', date: ' (date)', line: ' (performance)', points: ' (points)', label: ' (label)',
  title: '', day: ' (day)', month: ' (month)', price: ' (price)',
}
const GROUP_WORD = { fixture: 'Fixture', result: 'Result', milestone: 'Milestone', totw: 'Team of the week', stat: 'Stat', item: 'Event item' }
const SINGLE_LABEL = {
  'final.us': 'Our score', 'final.them': 'Opponent score', 'final.usOvers': 'Our overs', 'final.themOvers': 'Opponent overs', 'final.result': 'Result',
  'final.margin': 'Margin', 'final.winner': 'Winner', 'final.grade': 'Grade',
  'potm.name': 'Player of the match', 'potm.first': 'Player of the match (first name)', 'potm.last': 'Player of the match (last name)', 'potm.role': 'Player of the match (role)',
  'potm.bat': 'Player of the match (batting)', 'potm.bowl': 'Player of the match (bowling)', 'potm.line': 'Player of the match (performance)',
  'potm.summary': 'Player of the match (summary)', 'potm.photo': 'Player of the match (photo)',
  'toss.text': 'Toss', 'toss.winner': 'Toss winner', 'toss.decision': 'Toss decision',
  'announce.headline': 'Announcement headline', 'announce.subheadline': 'Announcement subheadline', 'announce.kind': 'Announcement kind',
  'announce.name': 'Announcement player', 'announce.first': 'Announcement player (first name)', 'announce.last': 'Announcement player (last name)', 'announce.photo': 'Announcement photo',
  'ms.title': 'Milestones title', 'tw.heading': 'Team of the week heading',
  'event.kicker': 'Event kicker', 'event.title': 'Event title', 'event.subtitle': 'Event subtitle', 'event.date': 'Event date', 'event.time': 'Event time',
  'event.venue': 'Event venue', 'event.price': 'Event price', 'event.cta': 'Event call to action', 'event.sponsor': 'Event sponsor', 'event.photo': 'Event photo',
}

export function postBindLabel(bind) {
  if (SINGLE_LABEL[bind]) return SINGLE_LABEL[bind]
  let m = (bind || '').match(/^(fixture|result|milestone|totw|stat|item)\.(\d+)\.(\w+)$/)
  if (m) return `${GROUP_WORD[m[1]]} ${m[2]}${FIELD_WORD[m[3]] ?? ` (${m[3]})`}`
  m = (bind || '').match(/^perf\.(us|them)\.(bat|bowl)\.(\d)\.(name|line)$/)
  if (m) return `${m[1] === 'us' ? 'Our' : 'Opponent'} ${m[2] === 'bat' ? 'batter' : 'bowler'} ${m[3]}${m[4] === 'line' ? ' (performance)' : ''}`
  return ''
}

// Photos are areas, not words.
export const isPostAreaBind = (bind) => /^(milestone|totw)\.\d+\.photo$/.test(bind || '') || /^(potm|announce|event)\.photo$/.test(bind || '')

// What a bound field prints from the post-type bundle (data.post). null when the editor holds nothing for
// that type yet, or the value is null (so the sample shows); '' when it holds the type but not this value.
export function resolvePostBind(bind, data = {}) {
  const post = data.post
  if (!post) return null
  let m = (bind || '').match(/^(fixture|result|milestone|totw|stat|item)\.(\d+)\.(\w+)$/)
  if (m) {
    const def = Object.values(LISTS).find((d) => d.group === m[1])
    const rows = post[def.rows]
    if (!Array.isArray(rows)) return null
    const row = rows[Number(m[2]) - 1]
    if (!row) return ''
    const v = row[m[3]]
    return v === undefined || v === null ? '' : String(v)
  }
  m = (bind || '').match(/^perf\.(us|them)\.(bat|bowl)\.(\d)\.(name|line)$/)
  if (m) {
    const rows = post.perf && post.perf[m[1]] && post.perf[m[1]][m[2]]
    if (!Array.isArray(rows)) return null
    const row = rows[Number(m[3]) - 1]
    return row ? String(row[m[4]] || '') : ''
  }
  m = (bind || '').match(/^(final|potm|toss|announce|event|ms|tw)\.(\w+)$/)
  if (m) {
    const group = post[m[1]]
    if (!group) return null
    const v = group[m[2]]
    // null is "not chosen yet" (the sample shows); undefined is a value the group does not have.
    return v === null ? null : v === undefined ? '' : String(v)
  }
  return null
}

// Which binds belong to which post type. A template marked as a type needs at least one of its own words,
// or nothing on the post would ever fill in.
export const TYPE_BINDS = {
  lineup: /^lineup\./,
  fixtures: /^fixture\./,
  results: /^result\.\d/,
  result: /^(final|potm|perf)\./,
  motm: /^(potm|stat)\./,
  totw: /^(totw|tw)\./,
  milestones: /^(milestone|ms)\./,
  announcement: /^announce\./,
  toss: /^toss\./,
  events: /^(event|item)\./,
}
export const hasTypeField = (type, binds) => !TYPE_BINDS[type] || (binds || []).some((b) => TYPE_BINDS[type].test(b || ''))

// What each type is called to a person.
export const TYPE_NAMES = {
  lineup: 'line up', fixtures: 'fixtures', results: 'results', result: 'final score', motm: 'player of the match',
  totw: 'team of the week', milestones: 'milestones', announcement: 'announcement', toss: 'toss', events: 'event',
}
