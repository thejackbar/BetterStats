// Fixtures for the layouts this group owns: { LAYOUT_ID: [Component, props, opts?] }.
// See base.jsx for the shared data and probe_layout_parts.jsx for the contract.
//
// EV7 to EV11 (event posters), EL1 to EL3 (event lists), MS1 and MS2 (milestones).
// Every conditional is on: price, time, venue, sponsor line, a photo, several items of each kind.
import React from 'react'
import { pal, team, opponent, match, players, meta, sponsors, club, PHOTO } from './base.jsx'
import { EVT_Kinetic, EVT_Swiss, EVT_Crest, EVT_Chalkboard, EVT_Polaroid, eventPaletteFor, prepareEventList } from '../../src/social/event-templates.jsx'
import { EVL_Agenda, EVL_Calendar, EVL_Cards } from '../../src/social/event-list-templates.jsx'
import { MilestoneCards, MilestoneBoard } from '../../src/social/milestone-templates.jsx'
void React; void opponent; void match; void players; void meta; void sponsors; void club

// What the editor hands an event poster (AdminSocialPost: extraProps.event and .motif).
const event = {
  kicker: 'SAVE THE DATE', title: 'Presentation Night', subtitle: 'Awards, a roast and a two course dinner for the whole club',
  date: 'SAT 14 NOV', time: '7:00 PM', venue: 'The Pavilion', price: '$55', cta: 'Book at the bar', sponsor: 'Acme Plumbing',
}
const motif = { key: 'star', icon: PHOTO, imageUrl: PHOTO, opacity: 0.85, label: 'Add a photo' }
const evProps = { team, event, motif, palette: pal }
const lightProps = { team, event, motif, palette: eventPaletteFor('light', pal) }

// An event list as the editor prepares it (prepareEventList): icons, a photo and a custom icon, two events
// on one day so the calendar legend shows both of its label shapes.
const list = prepareEventList({
  items: [
    { id: 'e1', date: '2026-11-03', title: 'Working Bee', time: '9:00 AM', venue: 'The Clubhouse', price: 'Free', iconKey: 'star', iconUri: '', imageUrl: '' },
    { id: 'e2', date: '2026-11-07', title: 'Quiz Night', time: '7:30 PM', venue: 'The Clubhouse', price: '$12', iconKey: 'target', iconUri: '', imageUrl: '' },
    { id: 'e3', date: '2026-11-14', title: 'Season Launch', time: '11:00 AM', venue: 'Home Ground', price: 'Free', iconKey: '', iconUri: '', imageUrl: PHOTO },
    { id: 'e4', date: '2026-11-14', title: 'Junior Clinic', time: '2:00 PM', venue: 'The Nets', price: '$5', iconKey: 'custom', iconUri: PHOTO, imageUrl: '' },
    { id: 'e5', date: '2026-11-21', title: 'Presentation Night', time: '7:00 PM', venue: 'The Pavilion', price: '$55', iconKey: 'trophy', iconUri: '', imageUrl: '' },
    { id: 'e6', date: '2026-11-28', title: 'Family Day', time: '10:00 AM', venue: 'Home Ground', price: '$10', iconKey: 'calendar', iconUri: '', imageUrl: '' },
  ],
})
const listEvent = { kicker: 'WHAT\'S ON', title: 'This Term', subtitle: 'Every event on the club calendar until Christmas', sponsor: 'Acme Plumbing' }
const lightList = { team, event: listEvent, list, palette: eventPaletteFor('light', pal) }
const darkList = { team, event: listEvent, list, palette: pal }

// Milestone cards as AdminSocialPost builds them (milestoneCards): a name, a photo, the big number, the unit
// and a date; and the meta with no heading typed, which is the layout's own MILE + STONES.
const milestones = [
  ['1,000', 'Career runs', '4 Oct'], ['100', 'Club games', '11 Oct'], ['50', 'Career wickets', '18 Oct'],
  ['200', 'Games in 1st Grade', '19 Oct'], ['25', 'Career catches', '25 Oct'], ['150', 'Club games', '26 Oct'],
].map(([value, unit, dateLabel], i) => ({
  key: `m${i}`, _id: `p${i + 1}`, first: `First${i + 1}`, last: `Last${i + 1}`, headshot: PHOTO, value, unit, dateLabel,
}))
const milestoneMeta = { title: '', round: 'ROUND 5', date: 'SAT 26 SEP', comp: 'PREMIER T20' }
const msProps = { palette: pal, team, milestones, milestoneMeta }

export const FIXTURES = {
  EV7: [EVT_Kinetic, evProps],
  EV8: [EVT_Swiss, lightProps],
  EV9: [EVT_Crest, evProps],
  EV10: [EVT_Chalkboard, evProps],
  EV11: [EVT_Polaroid, lightProps],
  EL1: [EVL_Agenda, darkList],
  EL2: [EVL_Calendar, lightList],
  EL3: [EVL_Cards, darkList],
  MS1: [MilestoneCards, msProps],
  MS2: [MilestoneBoard, msProps],
}
