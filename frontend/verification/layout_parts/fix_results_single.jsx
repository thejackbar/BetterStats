// Fixtures for the layouts this group owns: { LAYOUT_ID: [Component, props, opts?] }.
// See base.jsx for the shared data and probe_layout_parts.jsx for the contract.
import React from 'react'
import { pal, team, opponent, match, players, meta, sponsors, club, PHOTO, LOGO } from './base.jsx'
import { ResultMarginHero, ResultBroadcast, ResultVersusColumns, ResultStar, ResultInningsBars, ResultTicket } from '../../src/social/round-templates.jsx'
void React; void pal; void team; void opponent; void match; void players; void meta; void sponsors; void club

// The opposition has no crest here, so the badge letters (a colour part) show on their side. A decided single result shaped as the editor builds it for a 'singleresult' layout. We won, so the
// opposition side is the losing one on screen. Every conditional is on: grade, venue, POTM with photo, role,
// batting and bowling lines, three top batters and bowlers a side.
const perf = (rows) => rows.map(([n, l]) => ({ n, l, first: '', sn: '', o: '' }))
const result = {
  comp: 'PREMIER T20', grade: '1ST GRADE', round: 'ROUND 5', date: 'SAT 26 SEP', season: '2025/26', venue: 'HEATHCOTE RESERVE',
  us: { name: 'HOME CC', mono: 'HCC', logo: LOGO, score: '186/6', overs: '20.0' },
  them: { name: 'AWAY CC', mono: 'ACC', logo: null, score: '151/9', overs: '19.4' },
  winner: 'us',
  margin: 'BY 35 RUNS',
  potm: { first: 'First1', last: 'Last1', role: 'BATTER', bat: '87 (54)', bowl: '2/22', photo: PHOTO, line: '87 (54) · 2/22' },
  topBat: {
    us: perf([['LAST1', '87 (54)'], ['LAST2', '41 (30)'], ['LAST3', '22 (18)']]),
    them: perf([['LAST9', '56 (48)'], ['LAST10', '33 (29)'], ['LAST11', '18 (15)']]),
  },
  topBowl: {
    us: perf([['LAST4', '3/22'], ['LAST5', '2/28'], ['LAST6', '1/31']]),
    them: perf([['LAST12', '2/34'], ['LAST13', '2/41'], ['LAST14', '1/37']]),
  },
}
const props = { palette: pal, result, club, sponsors }
// RS4 draws the player's photo in a ring, or their initials when there is none. The initials colour can only
// show without a photo, so RS4 gets the same result with no photo.
const noPhoto = { ...props, result: { ...result, potm: { ...result.potm, photo: null } } }

export const FIXTURES = {
  RS1: [ResultMarginHero, props],
  RS2: [ResultBroadcast, props],
  RS3: [ResultVersusColumns, props],
  RS4: [ResultStar, noPhoto],
  RS5: [ResultInningsBars, props],
  RS6: [ResultTicket, props],
}
