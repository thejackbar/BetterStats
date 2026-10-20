// Fixtures for the layouts this group owns: { LAYOUT_ID: [Component, props, opts?] }.
// See base.jsx for the shared data and probe_layout_parts.jsx for the contract.
//
// T1 to T5, the lineup layouts. The props are what AdminSocialPost.jsx hands a lineup layout:
// team, opponent, match, players (playerToTemplatePlayer: first, last, role, captain, viceCaptain,
// keeper, debut, headshot, hero, _id), palette and headline, plus heroImage / featuredId / markHero /
// heroFocus for the layouts that draw a hero photo. Every conditional is on: a captain, a vice
// captain, a keeper, a debutant, a photo for every player, a headline, the hero row marked.
import React from 'react'
import { pal, team, opponent, match, players, PHOTO } from './base.jsx'
import { T1_HeroList, T2_CardGrid, T3_SideNumbered, T4_BattingOrder, T5_Brutalist } from '../../src/social/cricket-templates.jsx'
void React

// Eleven in the order: the 11th row is the one T4 marks. Roles cover BAT, BOWL, AR and WK so the role
// tag shows each kind; the first player is the captain, the second the vice captain, the fourth the
// keeper, and the third (and the ninth, who is not a leader) are on debut.
const squad = players.slice(0, 11).map((p, i) => ({
  first: p.first, last: p.last, role: p.role,
  roleLong: p.role, captain: i === 0, viceCaptain: i === 1, keeper: i === 3, debut: i === 2 || i === 8,
  headshot: p.headshot, hero: p.photo, _id: p._id, _name: p.name, totw: null,
}))

const base = { team, opponent, match, players: squad, palette: pal, headline: 'FIRST XI' }
// The hero layouts: a chosen player in the photo, marked on their row, plus the Hero Image upload.
const hero = { ...base, heroImage: PHOTO, featuredId: squad[4]._id, markHero: true, heroFocus: { x: 50, y: 0, scale: 1 } }

export const FIXTURES = {
  T1: [T1_HeroList, hero],
  T2: [T2_CardGrid, base],
  T3: [T3_SideNumbered, hero],
  T4: [T4_BattingOrder, base],
  T5: [T5_Brutalist, base],
}
