// Fixtures for the layouts this group owns: { LAYOUT_ID: [Component, props, opts?] }.
// See base.jsx for the shared data and probe_layout_parts.jsx for the contract.
//
// Club event posters EV1 to EV6. The editor hands each one `event` (the editor-driven copy),
// `motif` ({ icon, imageUrl, opacity, label }) and, for the light directions, a palette that
// eventPaletteFor has extended with `paper` and `deepInk`. Every conditional is on: price, time,
// venue, call to action and a sponsor line. EV1 draws the photo; EV2, EV3, EV4 and EV6 draw the
// motif icon; EV5 draws its "Add a photo" placeholder (the dotted frame with words on it).
import React from 'react'
import { pal, team, PHOTO } from './base.jsx'
import {
  EVT_Floodlit, EVT_Block, EVT_Ticket, EVT_Scoreboard, EVT_Gazette, EVT_Sticker,
  DEFAULT_EVENT, DEFAULT_EVENT_MOTIF, eventPaletteFor,
} from '../../src/social/event-templates.jsx'
void React

const event = { ...DEFAULT_EVENT, sponsor: 'Forno 47 Pizza' }
const iconMotif = { ...DEFAULT_EVENT_MOTIF, imageUrl: null }
const photoMotif = { ...DEFAULT_EVENT_MOTIF, imageUrl: PHOTO }
const dark = { team, event, palette: pal }
const light = { team, event, palette: eventPaletteFor('light', pal) }

export const FIXTURES = {
  EV1: [EVT_Floodlit, { ...dark, motif: photoMotif }],
  EV2: [EVT_Block, { ...dark, motif: iconMotif }],
  EV3: [EVT_Ticket, { ...light, motif: iconMotif }],
  EV4: [EVT_Scoreboard, { ...dark, motif: iconMotif }],
  EV5: [EVT_Gazette, { ...light, motif: iconMotif }],
  EV6: [EVT_Sticker, { ...light, motif: iconMotif }],
}
