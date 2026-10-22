// Fixtures for the layouts this group owns: { LAYOUT_ID: [Component, props, opts?] }.
// See base.jsx for the shared data and probe_layout_parts.jsx for the contract.
//
// The Results roundup layouts (RR1 to RR7). base.jsx `results` is a mix of wins and losses (4 W, 2 L), so
// a win colour and a loss colour are both on screen; the feature card of RR4 (the first row) is a win and the
// "other results" list holds the losses. RR7 needs top performers as arrays (up to two each), and a row with
// none, so the "no performer data" branch is exercised too.
import {
  ResultsList, ResultsScoreboard, ResultsRecord, ResultsHeadline, ResultsBoard, ResultsSplit, ResultsListLeaders,
} from '../../src/social/round-templates.jsx'
import { pal, meta, results, club, sponsors } from './base.jsx'

// The club mark the editor builds (name, full, mono, logo) rather than the base `club` shape.
const clubMark = { name: club.short, full: club.name, mono: club.mono, logo: club.logo }
const props = { palette: pal, meta, results, club: clubMark, sponsors }

const withLeaders = results.map((r, i) => ({
  ...r,
  topBat: i === 5 ? [] : [{ name: 'F. LAST1', line: '87 (54)' }, { name: 'F. LAST3', line: '41 (30)' }],
  topBowl: i === 5 ? [] : [{ name: 'F. LAST2', line: '3/22' }, { name: 'F. LAST4', line: '2/18' }],
}))

export const FIXTURES = {
  RR1: [ResultsList, props],
  RR2: [ResultsScoreboard, props],
  RR3: [ResultsRecord, props],
  RR4: [ResultsHeadline, props],
  RR5: [ResultsBoard, props],
  RR6: [ResultsSplit, props],
  RR7: [ResultsListLeaders, { ...props, results: withLeaders, perfSide: 'us' }],
}
