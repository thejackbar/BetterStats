// Fixtures for the layouts this group owns: { LAYOUT_ID: [Component, props, opts?] }.
// See base.jsx for the shared data and probe_layout_parts.jsx for the contract.
//
// T11 SplitPoster, T12 LineupCard, RS7 ResultGlass, RS8 ResultHighlights. Props are
// shaped as AdminSocialPost hands them over: lineup players are template players
// (first, last, captain, viceCaptain, keeper, debut, role, headshot, _id), a
// result is the `singleresult` object built around `extraProps.result`.
import React from 'react'
import { pal, team, opponent, match, players, meta, sponsors, club, PHOTO, LOGO } from './base.jsx'
import { SplitPoster } from '../../src/social/split-template.jsx'
import { LineupCard } from '../../src/social/lineup-card-template.jsx'
import { ResultGlass } from '../../src/social/result-glass-template.jsx'
import { ResultHighlights } from '../../src/social/highlights-cover-template.jsx'
void React; void players; void meta; void sponsors; void club

const ROLES = ['BAT', 'BOWL', 'AR', 'WK']
// Twelve names: past the eleven the layouts were first drawn for, every tag on.
const xi = Array.from({ length: 12 }, (_, i) => ({
  first: `First${i + 1}`, last: `LAST${i + 1}`, role: ROLES[i % 4], roleLong: ROLES[i % 4],
  captain: i === 0, viceCaptain: i === 1, keeper: i === 3, debut: i === 2 || i === 5,
  headshot: PHOTO, hero: null, _id: `p${i + 1}`, _name: `First${i + 1} Last${i + 1}`, totw: null,
}))

const lineupTeam = { name: team.name, fullName: team.fullName, short: team.short, monogram: team.monogram, logo: LOGO }
const lineupOpp = { name: opponent.name, short: opponent.short, monogram: opponent.monogram, logo: LOGO }
const lineupMatch = { ...match, season: '2025–26' }

// An in-photo player is marked on the list, a hero image fills the photo slot and
// the editor's own panel colour is left off (T11 then derives it from the accent).
const splitProps = {
  team: lineupTeam, opponent: lineupOpp, match: lineupMatch, players: xi, palette: pal,
  heroImage: PHOTO, headline: 'Senior', featuredId: 'p3', markHero: true, background: null,
}

// The card's saved look: a photo under a wash, so the wash layer and the photo both draw.
const cardProps = {
  team: lineupTeam, opponent: lineupOpp, match: lineupMatch, players: xi, palette: pal, headline: 'Senior',
  card: { bgUrl: PHOTO, wash: '', washOpacity: 0.8, corner: '', panel: '', logoUrl: '', logoScale: 1 },
  logoRatio: 1, sponsorCount: 3, sponsorPanel: 'light',
}

// The Glass Card: "us" has batted (a hundred, so the gold figure shows) and won; "them"
// have not batted, so the "Yet to bat" line is on the post as well as the rows.
const glassResult = {
  comp: 'PREMIER T20', grade: '1st Grade', round: 'ROUND 5', date: 'SAT 26 SEP', season: '2025/26', venue: 'Heathcote Reserve',
  us: { name: 'HOME CC', mono: 'HCC', logo: LOGO, score: '4/242', overs: '20' },
  them: { name: 'AWAY CC', mono: 'ACC', logo: LOGO, score: '—', overs: '' },
  winner: 'us', margin: 'BY 30 RUNS',
  potm: { first: '', last: '', role: '', bat: '', bowl: '', photo: null, line: '' },
  topBat: {
    us: [{ n: 'J. SMITH', l: '104 (88)', first: 'Jack', sn: 'Smith', o: '' }, { n: 'T. BROWN', l: '53 (41)', first: 'Tom', sn: 'Minter-Brown', o: '' }, { n: 'A. LEE', l: '22 (19)', first: 'Alex', sn: 'Lee', o: '' }],
    them: [],
  },
  topBowl: {
    us: [{ n: 'S. JONES', l: '5/22', first: 'Sam', sn: 'Jones', o: '4' }, { n: 'R. KHAN', l: '2/30', first: 'Raj', sn: 'Khan', o: '4' }, { n: 'B. COX', l: '1/18', first: 'Ben', sn: 'Cox', o: '3' }],
    them: [],
  },
}

// The cover: the other side batted first, ours won, so both rows and the trophy draw.
const highlightsResult = {
  comp: 'PREMIER T20', grade: '1st Grade', round: 'ROUND 5', date: 'SAT 26 SEP', season: '2025/26', venue: 'Heathcote Reserve',
  us: { name: 'HOME CC', mono: 'HCC', logo: null, score: '4/242', overs: '20' },
  them: { name: 'AWAY CC', mono: 'ACC', logo: null, score: '9/212', overs: '20' },
  winner: 'us', battedFirst: 'them', margin: 'BY 30 RUNS', title: 'Round Highlights',
}

export const FIXTURES = {
  T11: [SplitPoster, splitProps],
  T12: [LineupCard, cardProps],
  RS7: [ResultGlass, {
    palette: pal, result: glassResult, photo: PHOTO, sponsorCount: 3,
    look: { position: 'top-center', tint: 0.55, perfUs: 'bat', perfThem: 'bat' }, focus: { x: 50, y: 50, scale: 1 },
  }],
  RS8: [ResultHighlights, { palette: pal, result: highlightsResult, photo: PHOTO, sponsorCount: 3, focus: { x: 50, y: 30, scale: 1 } }],
}
