// Pure checks for bound text fields: which words are a field, and what a field
// prints. Plain Node, no browser:  node frontend/verification/probe_bound_fields.mjs
import { readFileSync } from 'node:fs'
import { bindFromToken, bindLabel, resolveBind, boundSlotCount, splitPlayerName, autoMarks, isAreaBind } from '../src/social/boundResolve.js'
import { hasTypeField } from '../src/social/postFields.js'
let pass = 0, fail = 0
const eq = (name, got, want) => { const ok = JSON.stringify(got) === JSON.stringify(want); ok ? pass++ : fail++; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok ? '' : `  got ${JSON.stringify(got)} want ${JSON.stringify(want)}`}`) }

// Tokens
eq('player 1', bindFromToken('player 1'), 'lineup.1.name')
eq('{{Player 12}} with braces and caps', bindFromToken('{{Player 12}}'), 'lineup.12.name')
eq('player3 with no space', bindFromToken('player3'), 'lineup.3.name')
eq('player 4 first', bindFromToken('player 4 first'), 'lineup.4.first')
eq('player 4  LAST (spacing, case)', bindFromToken('player  4   LAST'), 'lineup.4.last')
eq('player 2 role', bindFromToken('player 2 role'), 'lineup.2.role')
eq('player 15 is the last slot', bindFromToken('player 15'), 'lineup.15.name')
eq('player 16 is past the lineup ceiling', bindFromToken('player 16'), null)
eq('player 0 is not a slot', bindFromToken('player 0'), null)
eq('opponent', bindFromToken('opponent'), 'opponent')
eq('date', bindFromToken('date'), 'match.date')
eq('venue', bindFromToken('Venue'), 'match.venue')
eq('captain', bindFromToken('captain'), 'captain')
eq('club maps to team', bindFromToken('club'), 'team')
eq('an unknown word is not guessed', bindFromToken('batsman 1'), null)
eq('empty is not a field', bindFromToken(''), null)
eq('player alone is not a field', bindFromToken('player'), null)
eq('player 1 banana is not a field', bindFromToken('player 1 banana'), null)

// The Canva app keeps its own copy of the token rules (canva-app/src/template/tokens.ts)
// and tests it against this same table, so the two cannot drift apart.
const shared = JSON.parse(readFileSync(new URL('../../canva-app/src/template/token-cases.json', import.meta.url), 'utf8'))
eq('the shared token table is not empty', shared.length > 10, true)
for (const c of shared) eq(`shared with Canva app: ${JSON.stringify(c.token)}`, bindFromToken(c.token), c.binding)

// Which words belong to which post type, shared with the Canva app the same way.
const typeCases = JSON.parse(readFileSync(new URL('../../canva-app/src/template/type-cases.json', import.meta.url), 'utf8'))
eq('the shared type table is not empty', typeCases.length > 10, true)
for (const c of typeCases) eq(`type ${c.type} with ${JSON.stringify(c.binds)}`, hasTypeField(c.type, c.binds), c.ok)

// A photo not chosen yet shows its label (null), a value the group lacks prints nothing ('').
eq('announcement photo is null with no player', resolveBind('announce.photo', { post: { announce: { photo: null } } }), null)
eq('a field the group does not have is blank', resolveBind('announce.name', { post: { announce: { kind: 'X' } } }), '')

// Labels
eq('label for a slot', bindLabel('lineup.3.last'), 'Player 3 (last name)')
eq('label for a match field', bindLabel('match.date'), 'Date')

// Resolve: a lineup of three
const data = {
  lineup: [
    { name: 'George Pullinger', first: 'George', last: 'Pullinger', role: 'Batter', captain: true },
    { name: 'Chris Hansberry', role: 'Bowler', keeper: true },
    { name: 'Timmins, Sam' },
  ],
  opponent: 'SOUTH PERTH', headline: null, team: { name: 'Scarborough', fullName: 'Scarborough Cricket Club' },
  match: { date: 'SAT 3 OCT', venue: 'Richardson Park' },
}
eq('slot 1 name', resolveBind('lineup.1.name', data), 'George Pullinger')
eq('slot 1 last uses the row\'s own last', resolveBind('lineup.1.last', data), 'Pullinger')
eq('slot 2 first is split from a bare name', resolveBind('lineup.2.first', data), 'Chris')
eq('slot 2 last is split from a bare name', resolveBind('lineup.2.last', data), 'Hansberry')
eq('slot 3 "Last, First" order is understood', resolveBind('lineup.3.first', data), 'Sam')
eq('slot 2 role', resolveBind('lineup.2.role', data), 'Bowler')
eq('slot 3 has no role: empty, not undefined', resolveBind('lineup.3.role', data), '')
eq('slot 4 is past the lineup: blank, not a sample', resolveBind('lineup.4.name', data), '')
eq('captain', resolveBind('captain', data), 'George Pullinger')
eq('keeper', resolveBind('keeper', data), 'Chris Hansberry')
eq('opponent', resolveBind('opponent', data), 'SOUTH PERTH')
eq('team prefers the full name', resolveBind('team', data), 'Scarborough Cricket Club')
eq('match date', resolveBind('match.date', data), 'SAT 3 OCT')
eq('a match field the editor does not hold is null', resolveBind('match.round', data), null)
eq('headline unset is null', resolveBind('headline', data), null)

// Resolve: nothing held yet shows the sample (null), never a crash
eq('empty lineup: slot is null so the sample shows', resolveBind('lineup.1.name', { lineup: [] }), null)
eq('no lineup key at all', resolveBind('lineup.1.name', {}), null)
eq('empty lineup: captain is null', resolveBind('captain', { lineup: [] }), null)
eq('captain not chosen in a real lineup is blank', resolveBind('captain', { lineup: [{ name: 'A B' }] }), '')
eq('no bind', resolveBind(null, data), null)
eq('a bind it does not know', resolveBind('whatever', data), null)


// Markers and photos (a template puts "C" or a photo beside every name; only the right ones print)
const MK = { lineup: [
  { name: 'A One', captain: true, photo: '/img/a.jpg' },
  { name: 'B Two', keeper: true, viceCaptain: true, debut: true },
  { name: 'C Three' },
] }
eq('captain mark prints C for the captain', resolveBind('lineup.1.captain', MK), 'C')
eq('captain mark is blank for another player', resolveBind('lineup.2.captain', MK), '')
eq('keeper mark prints WK', resolveBind('lineup.2.keeper', MK), 'WK')
eq('vice mark prints VC', resolveBind('lineup.2.vice', MK), 'VC')
eq('debut mark prints DEBUT', resolveBind('lineup.2.debut', MK), 'DEBUT')
eq('debut mark is blank when not a debutant', resolveBind('lineup.3.debut', MK), '')
eq('photo is the headshot address', resolveBind('lineup.1.photo', MK), '/img/a.jpg')
eq('a player with no photo prints nothing', resolveBind('lineup.3.photo', MK), '')
eq('a place beyond the lineup prints nothing', resolveBind('lineup.9.photo', MK), '')
eq('no lineup yet: a photo shows its placeholder (null)', resolveBind('lineup.1.photo', { lineup: [] }), null)
eq('no lineup yet: a mark shows its sample (null)', resolveBind('lineup.1.captain', {}), null)
eq('vice captain by name', resolveBind('vice', MK), 'B Two')
eq('keeper by name', resolveBind('keeper', MK), 'B Two')
eq('bindLabel for a photo', bindLabel('lineup.2.photo'), 'Player 2 (photo)')

// The featured photo, and marks that follow names on their own
eq('photo is the featured photo', bindFromToken('photo'), 'photo')
eq('player photo (no number) is the featured photo', bindFromToken('Player Photo'), 'photo')
eq('hero photo is the featured photo', bindFromToken('{{hero photo}}'), 'photo')
eq('the featured photo is an area', isAreaBind('photo'), true)
eq('a name is not an area', isAreaBind('lineup.1.name'), false)
eq('bindLabel of the featured photo', bindLabel('photo'), 'Featured photo')
eq('featured photo before any data is null (placeholder)', resolveBind('photo', {}), null)
eq('featured photo is the address the editor holds', resolveBind('photo', { featuredPhoto: '/img/x.jpg' }), '/img/x.jpg')
eq('featured photo is empty when players are held but none has one', resolveBind('photo', { featuredPhoto: '' }), '')
const AM = { lineup: [{ name: 'A One', captain: true }, { name: 'B Two', keeper: true, debut: true }, { name: 'C Three', captain: true, viceCaptain: false, keeper: true }, { name: 'D Four' }] }
eq('automatic mark for a captain', autoMarks('lineup.1.name', AM), ' (C)')
eq('automatic marks combine for one player', autoMarks('lineup.2.name', AM), ' (WK, DEBUT)')
eq('captain and keeper together', autoMarks('lineup.3.name', AM), ' (C, WK)')
eq('no marks for an ordinary player', autoMarks('lineup.4.name', AM), '')
eq('marks follow the last-name field too', autoMarks('lineup.1.last', AM), ' (C)')
eq('but not the first-name field (it would print twice)', autoMarks('lineup.1.first', AM), '')
eq('marks can be switched off', autoMarks('lineup.1.name', { ...AM, marksOn: false }), '')
eq('a place beyond the lineup has none', autoMarks('lineup.9.name', AM), '')

// Logos (crests)
eq('logo is the club crest', bindFromToken('logo'), 'logo.team')
eq('club logo', bindFromToken('{{Club Logo}}'), 'logo.team')
eq('crest', bindFromToken('crest'), 'logo.team')
eq('opponent logo', bindFromToken('opponent logo'), 'logo.opponent')
eq('opposition crest', bindFromToken('opposition crest'), 'logo.opponent')
eq('logo 2 is not a field', bindFromToken('logo 2'), null)
eq('a logo is an area', isAreaBind('logo.team') && isAreaBind('logo.opponent'), true)
eq('labels', [bindLabel('logo.team'), bindLabel('logo.opponent')], ['Club logo', 'Opponent logo'])
eq('club logo before any data is null (placeholder)', resolveBind('logo.team', {}), null)
eq('club logo is the address the editor holds', resolveBind('logo.team', { teamLogo: '/c.png' }), '/c.png')
eq('a club with no logo prints nothing', resolveBind('logo.team', { teamLogo: '' }), '')
eq('opponent logo before an opponent is chosen is null', resolveBind('logo.opponent', { opponent: null, opponentLogo: null }), null)
eq('an opponent with no logo prints nothing', resolveBind('logo.opponent', { opponent: 'South Perth', opponentLogo: null }), '')
eq('an opponent logo is the address held', resolveBind('logo.opponent', { opponent: 'South Perth', opponentLogo: '/o.png' }), '/o.png')

// The other post types: what a bound field prints from the post bundle (data.post)
const POST = {
  fixtures: [{ grade: '1ST XI', opponent: 'SUBIACO', short: 'SUB', homeaway: 'HOME', time: '12:30 PM', venue: 'TOMPKINS PARK' }],
  results: [{ grade: '2ND XI', opponent: 'WILLETTON', us: '176', them: '9/201', outcome: 'LOSS', margin: 'BY 25 RUNS' }],
  stats: [{ label: 'Runs', value: '87' }, { label: 'SR', value: '' }],
  milestones: [{ name: 'George Pullinger', value: '200', unit: 'GAMES', date: '4 Oct', photo: '/p.jpg' }],
  totw: [{ name: 'A One', line: '5/22', points: 80, photo: '' }],
  items: [{ title: 'Quiz Night', date: 'Fri 24 Oct', venue: 'Clubhouse' }],
  final: { us: '6/188', them: '184', result: 'WIN', margin: 'BY 4 WICKETS', winner: 'SCARBOROUGH' },
  potm: { name: 'George Pullinger', first: 'George', last: 'Pullinger', photo: '/h.jpg', summary: '' },
  toss: { text: 'SCARBOROUGH WON THE TOSS AND ELECTED TO BAT', winner: 'SCARBOROUGH', decision: 'BAT' },
  announce: { headline: 'NAMED CAPTAIN', subheadline: 'FOR 2025-26', photo: '/a.jpg' },
  event: { title: 'Curry Night', photo: '' },
  ms: { title: 'Milestones' }, tw: { heading: 'SENIOR' },
  perf: { us: { bat: [{ name: 'J. Barendse', line: '64 (71)' }], bowl: [] }, them: { bat: [], bowl: [{ name: 'T. Hughes', line: '3/44' }] } },
}
const D = { post: POST }
eq('fixture 1 grade', resolvePostBindProbe('fixture.1.grade'), '1ST XI')
function resolvePostBindProbe(b) { return resolveBind(b, D) }
eq('fixture 1 venue', resolveBind('fixture.1.venue', D), 'TOMPKINS PARK')
eq('a fixture row that is not held prints nothing', resolveBind('fixture.5.venue', D), '')
eq('result 1 us and them', [resolveBind('result.1.us', D), resolveBind('result.1.them', D)], ['176', '9/201'])
eq('stat 1', [resolveBind('stat.1.label', D), resolveBind('stat.1.value', D)], ['Runs', '87'])
eq('an empty stat value is empty', resolveBind('stat.2.value', D), '')
eq('milestone value and photo', [resolveBind('milestone.1.value', D), resolveBind('milestone.1.photo', D)], ['200', '/p.jpg'])
eq('totw line', resolveBind('totw.1.line', D), '5/22')
eq('totw points is text', resolveBind('totw.1.points', D), '80')
eq('event item title', resolveBind('item.1.title', D), 'Quiz Night')
eq('final score', [resolveBind('final.us', D), resolveBind('final.them', D), resolveBind('final.result', D)], ['6/188', '184', 'WIN'])
eq('potm last', resolveBind('potm.last', D), 'Pullinger')
eq('toss text', resolveBind('toss.text', D), 'SCARBOROUGH WON THE TOSS AND ELECTED TO BAT')
eq('announcement headline', resolveBind('announce.headline', D), 'NAMED CAPTAIN')
eq('event title', resolveBind('event.title', D), 'Curry Night')
eq('milestones title', resolveBind('ms.title', D), 'Milestones')
eq('team of the week heading', resolveBind('tw.heading', D), 'SENIOR')
eq('our batter 1', [resolveBind('perf.us.bat.1.name', D), resolveBind('perf.us.bat.1.line', D)], ['J. Barendse', '64 (71)'])
eq('their bowler line', resolveBind('perf.them.bowl.1.line', D), '3/44')
eq('an empty performance list prints nothing', resolveBind('perf.us.bowl.1.name', D), '')
eq('no post bundle: a fixture shows its sample (null)', resolveBind('fixture.1.venue', {}), null)
eq('no post bundle: the final score shows its sample (null)', resolveBind('final.us', {}), null)
eq('a type the bundle does not hold is null, not blank', resolveBind('toss.text', { post: { fixtures: [] } }), null)
eq('a group the post holds but a missing field is blank', resolveBind('potm.role', D), '')
eq('post photos are areas', ['milestone.1.photo', 'totw.2.photo', 'potm.photo', 'announce.photo', 'event.photo'].every((b) => isAreaBind(b)), true)
eq('a fixture venue is not an area', isAreaBind('fixture.1.venue'), false)

// Counting slots
eq('slot count is the highest slot used', boundSlotCount([{ bind: 'lineup.3.name' }, { bind: 'lineup.11.last' }, { bind: 'opponent' }, {}]), 11)
eq('no player slots', boundSlotCount([{ bind: 'opponent' }]), 0)
eq('split: "Last, First"', splitPlayerName('Allen, Matt'), ['Matt', 'Allen'])
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
