// Pure checks for bound text fields: which words are a field, and what a field
// prints. Plain Node, no browser:  node frontend/verification/probe_bound_fields.mjs
import { bindFromToken, bindLabel, resolveBind, boundSlotCount, splitPlayerName } from '../src/social/boundResolve.js'
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

// Counting slots
eq('slot count is the highest slot used', boundSlotCount([{ bind: 'lineup.3.name' }, { bind: 'lineup.11.last' }, { bind: 'opponent' }, {}]), 11)
eq('no player slots', boundSlotCount([{ bind: 'opponent' }]), 0)
eq('split: "Last, First"', splitPlayerName('Allen, Matt'), ['Matt', 'Allen'])
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
