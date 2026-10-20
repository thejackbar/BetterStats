// Fixtures for the layouts this group owns: { LAYOUT_ID: [Component, props, opts?] }.
// See base.jsx for the shared data and probe_layout_parts.jsx for the contract.
// FX1 to FX6: fixtures roundups. Props are shaped as the editor passes them
// (AdminSocialPost: palette, meta { round, date, comp, season }, fixtures, club, sponsors).
import React from 'react'
import { pal, meta, sponsors, club } from './base.jsx'
import { FixtureList, FixtureHype, FixtureGrid, FixtureBoard, FixtureHeadline, FixtureSchedule } from '../../src/social/round-templates.jsx'
void React

// Seven rows, home and away mixed, every field filled, times out of order (FX6 sorts them).
// No opponent logo, so the monogram circle (text, fill, ring) is on screen.
const TIMES = ['1:00 PM', '10:30 AM', '12:00 PM', '2:00 PM', '9:00 AM', '11:00 AM', '1:30 PM']
const fixtures = TIMES.map((time, i) => ({
  grade: `${i + 1}ND GRADE`, opp: `OPPONENT ${i + 1}`, oppMono: `O${i + 1}`, oppLogo: null,
  ha: i % 2 === 0 ? 'H' : 'A', time, venue: `GROUND ${i + 1}`,
}))
const fxMeta = { round: meta.round, date: meta.date, comp: meta.comp, season: meta.season }
const fxClub = { name: club.name, full: 'Home Cricket Club', mono: club.mono, logo: club.logo }
const props = { palette: pal, meta: fxMeta, fixtures, club: fxClub, sponsors }

export const FIXTURES = {
  FX1: [FixtureList, props],
  FX2: [FixtureHype, props],
  FX3: [FixtureGrid, props],
  FX4: [FixtureBoard, props],
  FX5: [FixtureHeadline, props],
  FX6: [FixtureSchedule, props],
}
