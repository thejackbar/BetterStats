// Team of the week (done in v9.126.0): the reference for how a fixture reads.
import { TeamOfWeekGrid, TeamOfWeekBoard } from '../../src/social/totw-templates.jsx'
import { pal, team, players, meta } from './base.jsx'
const totw = { round: meta.round, date: meta.date, comp: meta.comp, showPoints: true, heading: 'SENIOR' }
const props = { palette: pal, team, players: players.slice(0, 11), totw }
export const FIXTURES = { TW1: [TeamOfWeekGrid, props], TW2: [TeamOfWeekBoard, props] }
