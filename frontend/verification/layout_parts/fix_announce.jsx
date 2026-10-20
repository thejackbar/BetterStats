// Fixtures for the layouts this group owns: { LAYOUT_ID: [Component, props, opts?] }.
// See base.jsx for the shared data and probe_layout_parts.jsx for the contract.
//
// C1, C5 (announcement), C2 (toss), C3 (man of the match), C4 (final score) and T13 (round cover).
// Props are shaped the way AdminSocialPost builds them around `extraProps`. Every conditional is on:
// a photo, a sub-headline, four stat tiles and a summary, a winner on our side with both sets of
// performers, a player of the match with figures, a sponsor count (so the sponsor room is kept).
import React from 'react'
import { C1_CaptainAnnounce, C2_TossWon, C3_ManOfMatch, C4_FinalScore } from '../../src/social/cricket-templates.jsx'
import { GiantType } from '../../src/social/giant-type-template.jsx'
import { RoundCover } from '../../src/social/round-cover-template.jsx'
import { pal, team, opponent, match, players, PHOTO } from './base.jsx'
void React

const star = { ...players[0], first: 'Jordan', last: 'Smith', role: 'BAT', roleLong: 'Opening batter', headshot: PHOTO }

const announcement = { kind: 'APPOINTMENT', headline: 'NAMED CAPTAIN', subheadline: 'FOR THE 2025-26 SEASON', player: star }
const giantAnnouncement = { kind: 'MILESTONE', headline: '100', subheadline: '100* · 83 balls · 12 fours', player: star }
const toss = { winner: 'TEAM', decision: 'BAT' }
const motm = {
  player: star,
  stats: [{ label: 'Runs', value: '87' }, { label: 'Balls', value: '54' }, { label: 'Wickets', value: '2' }, { label: 'Catches', value: '1' }],
  summary: 'Held the innings together when it mattered.',
}
const perf = (n, kind) => Array.from({ length: n }, (_, i) => ({ last: `Last${i + 1}`, line: kind === 'bat' ? `${87 - i * 12} (${54 - i * 6})` : `${3 - i}/${22 + i * 5}` }))
const result = {
  winner: 'TEAM', margin: 'BY 30 RUNS', grade: '1ST GRADE', teamScore: '180/6', oppScore: '150/9',
  motmFirst: 'Jordan', motmLast: 'Smith', motmBat: '87 (54)', motmBowl: '2/22',
  topBatters: { team: perf(3, 'bat'), opponent: perf(3, 'bat') },
  topBowlers: { team: perf(3, 'bowl'), opponent: perf(3, 'bowl') },
}

export const FIXTURES = {
  C1: [C1_CaptainAnnounce, { palette: pal, team, opponent, match, announcement }],
  C2: [C2_TossWon, { palette: pal, team, opponent, match, toss }],
  C3: [C3_ManOfMatch, { palette: pal, team, opponent, match, motm }],
  C4: [C4_FinalScore, { palette: pal, team, opponent, match, result }],
  C5: [GiantType, { palette: pal, team, opponent, match, announcement: giantAnnouncement, sponsorCount: 3 }],
  T13: [RoundCover, { palette: pal, team, opponent, match, heroImage: PHOTO, headline: 'SENIOR', sponsorCount: 3 }],
}
