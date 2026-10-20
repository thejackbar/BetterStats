// Fixtures for the layouts this group owns: { LAYOUT_ID: [Component, props, opts?] }.
// See base.jsx for the shared data and probe_layout_parts.jsx for the contract.
// T6 Diagonal, T7 Captain Spotlight, T8 Mosaic, T9 Flyer, T10 Team Sheet.
import React from 'react'
import { T6_Diagonal, T7_CaptainSpotlight, T8_Mosaic, T9_Flyer, T10_TeamSheet } from '../../src/social/cricket-templates.jsx'
import { pal, team, opponent, match, players, meta, sponsors, club, PHOTO } from './base.jsx'
void React; void meta; void sponsors; void club

// The lineup layouts read the editor's player shape (playerToTemplatePlayer in
// AdminSocialPost.jsx): first / last / role / roleLong and the captain, vice
// captain, keeper and debut flags. The base players use other names for some of
// those, so they are mapped here. A full XI plus two: every role, every mark.
const ROLE_LONG = { BAT: 'Batter', BOWL: 'Bowler', AR: 'All-Rounder', WK: 'Wicket-Keeper' }
const xi = players.slice(0, 13).map((p, i) => ({
  first: p.first, last: p.last, role: p.role, roleLong: ROLE_LONG[p.role] || p.role,
  captain: i === 0, viceCaptain: i === 1, keeper: i === 3, debut: i === 2 || i === 6,
  headshot: PHOTO, hero: PHOTO, _id: p._id, _name: p.name, totw: null,
}))
// The editor hands the layouts the match as typed: all six fields filled.
const m = { ...match }
const common = { palette: pal, team, opponent, match: m, players: xi }

export const FIXTURES = {
  T6: [T6_Diagonal, { ...common, heroImage: PHOTO, featuredId: xi[0]._id }],
  T7: [T7_CaptainSpotlight, {
    ...common, heroImage: PHOTO,
    milestone: { value: '200', unit: 'GAMES', reason: 'MILESTONE', detail: 'Batter and captain', player: xi[0] },
  }],
  T8: [T8_Mosaic, { ...common, headline: '1st XI', featuredIdx: 0 }],
  T9: [T9_Flyer, { ...common, headline: '1st XI' }],
  T10: [T10_TeamSheet, { ...common, heroImage: PHOTO, headline: '1st XI', featuredId: xi[0]._id, markHero: true }],
}
