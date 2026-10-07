// Renders every BetterPosts layout on the server with marker text in Headline and
// Competition and reports which layouts print each. The editor's Match Info panel
// keeps its own list of the layouts that draw a Headline; this proves that list.
// Run: node verification/probe_match_info_fields.mjs   (bundled by the .mjs wrapper)
import React from 'react'
import { renderToString } from 'react-dom/server'
import * as cricket from '../src/social/cricket-templates.jsx'
import * as rounds from '../src/social/round-templates.jsx'
import * as split from '../src/social/split-template.jsx'
import * as card from '../src/social/lineup-card-template.jsx'
import * as totw from '../src/social/totw-templates.jsx'
import * as glass from '../src/social/result-glass-template.jsx'

const HEAD = 'ZZHEADLINEZZ', COMP = 'ZZCOMPZZ'
const pal = { primary: '#102040', secondary: '#183060', accent: '#f0b000', ink: '#ffffff', name: 'x' }
const player = (i) => ({ id: 'p' + i, first: 'First' + i, last: 'Last' + i, role: 'BAT', headshot: null })
const players = Array.from({ length: 11 }, (_, i) => player(i))
const team = { name: 'Home CC', monogram: 'HCC', logo: null, fullName: 'Home Cricket Club' }
const opponent = { name: 'Away CC', monogram: 'ACC', logo: null }
const match = { competition: COMP, round: 'ROUND 1', venue: 'HOME GROUND', date: 'SAT 1 JAN', time: '1:00 PM', season: '2025-26' }
const meta = { round: 'ROUND 1', date: 'SAT 1 JAN', comp: COMP, season: '2025-26' }
const fx = Array.from({ length: 5 }, (_, i) => ({ id: i, grade: 'A', opp: 'Opp' + i, oppMono: 'OP', date: 'SAT', time: '1:00 PM', venue: 'V', home: true }))
const rs = Array.from({ length: 5 }, (_, i) => ({ id: i, grade: 'A', opp: 'Opp' + i, oppMono: 'OP', outcome: 'W', us: '1/100', them: '2/90', margin: 'BY 5 RUNS' }))
const result = { comp: COMP, grade: '', round: 'ROUND 1', date: 'SAT 1 JAN', season: '2025-26', venue: 'V',
  us: { name: 'Home', mono: 'H', score: '1/100', overs: '20' }, them: { name: 'Away', mono: 'A', score: '2/90', overs: '20' }, winner: 'us', margin: 'BY 5 RUNS',
  potm: { first: 'A', last: 'B', role: '', bat: '', bowl: '' }, topBatters: [], topBowlers: [] }

const lineupProps = { team, opponent, match, players, palette: pal, headline: HEAD, width: 1080, height: 1080 }
const LAYOUTS = {
  T1: [cricket.T1_HeroList, lineupProps], T2: [cricket.T2_CardGrid, lineupProps], T3: [cricket.T3_SideNumbered, lineupProps],
  T4: [cricket.T4_BattingOrder, lineupProps], T5: [cricket.T5_Brutalist, lineupProps], T6: [cricket.T6_Diagonal, lineupProps],
  T7: [cricket.T7_CaptainSpotlight, lineupProps], T8: [cricket.T8_Mosaic, lineupProps], T9: [cricket.T9_Flyer, lineupProps],
  T10: [cricket.T10_TeamSheet, lineupProps], T11: [split.SplitPoster, lineupProps], T12: [card.LineupCard, lineupProps],
  C2: [cricket.C2_TossWon, { ...lineupProps, toss: { winner: 'TEAM', decision: 'BAT' } }],
  FX1: [rounds.FixtureList, { palette: pal, meta, fixtures: fx, club: {} }], FX2: [rounds.FixtureHype, { palette: pal, meta, fixtures: fx, club: {} }],
  FX3: [rounds.FixtureGrid, { palette: pal, meta, fixtures: fx, club: {} }], FX4: [rounds.FixtureBoard, { palette: pal, meta, fixtures: fx, club: {} }],
  FX5: [rounds.FixtureHeadline, { palette: pal, meta, fixtures: fx, club: {} }], FX6: [rounds.FixtureSchedule, { palette: pal, meta, fixtures: fx, club: {} }],
  RR1: [rounds.ResultsList, { palette: pal, meta, results: rs, club: {} }], RR7: [rounds.ResultsListLeaders, { palette: pal, meta, results: rs, club: {} }],
  RR2: [rounds.ResultsScoreboard, { palette: pal, meta, results: rs, club: {} }], RR3: [rounds.ResultsRecord, { palette: pal, meta, results: rs, club: {} }],
  RR4: [rounds.ResultsHeadline, { palette: pal, meta, results: rs, club: {} }], RR5: [rounds.ResultsBoard, { palette: pal, meta, results: rs, club: {} }],
  RR6: [rounds.ResultsSplit, { palette: pal, meta, results: rs, club: {} }],
  RS1: [rounds.ResultMarginHero, { palette: pal, result }], RS2: [rounds.ResultBroadcast, { palette: pal, result }],
  RS3: [rounds.ResultVersusColumns, { palette: pal, result }], RS4: [rounds.ResultStar, { palette: pal, result }],
  RS5: [rounds.ResultInningsBars, { palette: pal, result }], RS6: [rounds.ResultTicket, { palette: pal, result }],
  RS7: [glass.ResultGlass, { palette: pal, result }],
  TW1: [totw.TeamOfWeekGrid, { palette: pal, players, totw: { round: 'ROUND 1', date: 'SAT 1 JAN', comp: COMP, showPoints: true } }],
  TW2: [totw.TeamOfWeekBoard, { palette: pal, players, totw: { round: 'ROUND 1', date: 'SAT 1 JAN', comp: COMP, showPoints: true } }],
}
const out = {}
for (const [id, [C, props]] of Object.entries(LAYOUTS)) {
  try {
    const html = renderToString(React.createElement(C, { width: 1080, height: 1080, ...props }))
    out[id] = { headline: html.includes(HEAD), competition: html.includes(COMP) }
  } catch (e) { out[id] = { error: String(e.message).slice(0, 90) } }
}
console.log(JSON.stringify(out, null, 1))
