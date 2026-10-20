// Fixtures for the layouts this group owns: { LAYOUT_ID: [Component, props, opts?] }.
// See base.jsx for the shared data and probe_layout_parts.jsx for the contract.
//
// The full scorecards (SC1 Broadcast, SC2 Brutalist, SC3 Dashboard) take the same props the editor gives
// them: `{ match, palette }` with `match = { meta, home, away }` (AdminSocialPost's DEFAULT_SCORECARD
// shape). They are fixed at 1920x1080 and have no size picker, so the only size is the wide one. The
// square-split variant is the same code with `square` and `only`; it is not rendered by the probe.
//
// Every conditional is on: a not-out batter, a did-not-bat row, role tags, a first name and a bare surname,
// an extras line with penalty runs, a bowler with wickets and one without, a club crest on one side and
// none on the other, a sponsor logo in one slot and the empty placeholder in the other, and a player of
// the match.
import { SC1_Broadcast, SC2_Brutalist, SC3_Dashboard } from '../../src/social/cricket-templates.jsx'
import { pal, LOGO } from './base.jsx'

const bat = (num, first, last, extra = {}) => ({
  num, first, last, r: 20 + num * 4, b: 18 + num * 3, fours: num % 4, sixes: num % 3, sr: 110.5,
  out: num % 2 ? `c Fielder${num} b Bowler${num}` : `b Bowler${num}`, notOut: false, didNotBat: false, role: null, ...extra,
})
const bowl = (i, first, last, w) => ({ first, last, o: `${3 + (i % 2)}.0`, m: i % 2, r: 22 + i * 3, w, econ: 7.25 + i * 0.4 })

const side = (name, short, color, tag, logo) => ({
  name, short, color, monogram: short, logo, headerInk: '#0a0a0a',
  total: '186', overs: '19.3', wickets: 6, runRate: '9.54',
  batting: [
    bat(1, 'Sam', `${tag}ONE`, { role: 'c' }),
    bat(2, 'Jack', `${tag}TWO`),
    bat(3, 'Liam', `${tag}THREE`, { role: 'wk' }),
    bat(4, '', `${tag}FOUR`),
    bat(5, 'Noah', `${tag}FIVE`, { out: 'not out', notOut: true, r: 41 }),
    bat(6, 'Oscar', `${tag}SIX`, { out: 'not out', notOut: true, r: 12 }),
    bat(7, 'Eli', `${tag}SEVEN`, { didNotBat: true, out: '', r: 0, b: 0, fours: 0, sixes: 0 }),
  ],
  bowling: [
    bowl(0, 'Will', `${tag}BOWL1`, 3),
    bowl(1, 'Max', `${tag}BOWL2`, 2),
    bowl(2, '', `${tag}BOWL3`, 0),
    bowl(3, 'Finn', `${tag}BOWL4`, 1),
  ],
  extras: { total: 24, b: 4, lb: 3, nb: 5, wd: 8, pr: 4 },
})

const scMatch = {
  meta: {
    competition: 'PREMIER T20', round: 'ROUND 5', format: 'T20', overs: 20, venue: 'HEATHCOTE RESERVE', date: 'SAT 26 SEP',
    toss: 'HOME WON THE TOSS · ELECTED TO BAT', result: 'HOME WON BY 6 WICKETS', series: 'SEASON 2025/26',
    motm: { first: 'Sam', last: 'HOMEONE', team: 'HOME', line: '87 (54) · 2/22' },
    sponsors: [{ url: LOGO, name: 'Sponsor One' }, { url: null, name: '' }],
  },
  home: side('HOME CRICKET CLUB', 'HCC', '#1a4eb8', 'HOME', LOGO),
  away: side('AWAY CRICKET CLUB', 'ACC', '#cc1f2c', 'AWAY', null),
}
const props = { match: scMatch, palette: pal }
const opts = { sizes: [[1920, 1080]] }

export const FIXTURES = {
  SC1: [SC1_Broadcast, props, opts],
  SC2: [SC2_Brutalist, props, opts],
  SC3: [SC3_Dashboard, props, opts],
}
