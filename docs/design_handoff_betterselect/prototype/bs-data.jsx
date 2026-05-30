/* bs-data.jsx — mock club-cricket data for the BetterSelect redesign.
   Shapes mirror the real app: players annotated with availability, squads,
   skill attributes, clash detection; fixtures keyed by date. */

// Availability status identity (mirrors lib/availability.js)
const BS_AVAIL = {
  AVAILABLE:   { label: 'Available',   short: 'In',     glyph: '✓', dot: '#16c784', tint: 'rgba(22,199,132,0.10)', text: '#16c784', rank: 0 },
  MAYBE:       { label: 'Maybe',       short: 'Maybe',  glyph: '?', dot: '#f5b542', tint: 'rgba(245,181,66,0.10)', text: '#f5b542', rank: 1 },
  NO_RESPONSE: { label: 'No response', short: 'No reply',glyph: '–', dot: '#3a3f50', tint: 'transparent',          text: '#5b6072', rank: 2 },
  UNAVAILABLE: { label: 'Unavailable', short: 'Out',    glyph: '✕', dot: '#ef5b5b', tint: 'rgba(239,91,91,0.07)',  text: '#ef5b5b', rank: 3 },
};
const BS_AVAIL_ORDER = ['AVAILABLE', 'MAYBE', 'NO_RESPONSE', 'UNAVAILABLE'];

// Skill role identity
const BS_ROLES = {
  BAT: { label: 'Batter',       short: 'BAT', glyph: '🏏' },
  BWL: { label: 'Bowler',       short: 'BWL', glyph: '⚐' },
  ALL: { label: 'All-rounder',  short: 'ALL', glyph: '✦' },
  WKT: { label: 'Keeper',       short: 'WK',  glyph: '✛' },
};

const BS_BOWL = {
  FAST: 'Fast', FAST_MEDIUM: 'Fast-medium', MEDIUM: 'Medium',
  OFF_SPIN: 'Off spin', LEG_SPIN: 'Leg spin', LEFT_ARM_ORTHODOX: 'SLA', NONE: '',
};

// The club + this weekend's fixture we're picking for.
const BS_CLUB = { name: 'Applecross CC', short: 'ACC', accent: '#16c784' };

const BS_FIXTURE = {
  id: 'fx-1',
  team: '1st XI',
  grade: 'A-Grade',
  opponent: 'Nedlands',
  home_away: 'HOME',
  venue: 'Tompkins Park',
  round: 9,
  played_on: '2026-06-06',
  date_label: 'Sat 6 Jun',
  start_time: '12:30 PM',
  format: 11,
};

// Upcoming dates for the availability matrix (Saturdays).
const BS_DATES = [
  { date: '2026-06-06', label: 'Sat 6 Jun', sub: 'R9 · vs Nedlands', current: true },
  { date: '2026-06-13', label: 'Sat 13 Jun', sub: 'R10 · @ Fremantle' },
  { date: '2026-06-20', label: 'Sat 20 Jun', sub: 'R11 · vs Melville' },
  { date: '2026-06-27', label: 'Sat 27 Jun', sub: 'R12 · @ Willetton' },
];

// id, name, roles[], bat hand, bowl type, squads[], availability for 6 Jun,
// is_dormant, clash (other team same day), batting position hint, form (last 5 scores)
function mk(id, name, roles, bat, bowl, squads, avail, extra = {}) {
  return {
    id, name, roles, bat, bowl, squads, avail,
    dormant: extra.dormant || false,
    clash: extra.clash || null,
    keeperPref: roles.includes('WKT'),
    captainPref: extra.captain || false,
    form: extra.form || null,
    note: extra.note || null,
  };
}

const BS_PLAYERS = [
  mk('p1',  'Jack Barendse',    ['BAT'],        'RHB', 'NONE',              ['1st XI'],          'AVAILABLE',   { captain: true, form: [72, 14, 103, 0, 41], note: 'Capt · 412 runs this season' }),
  mk('p2',  'Tom Petersen',     ['BAT','WKT'],  'LHB', 'NONE',              ['1st XI'],          'AVAILABLE',   { form: [33, 51, 8, 27, 44] }),
  mk('p3',  'Riley Mostyn',     ['ALL'],        'RHB', 'FAST_MEDIUM',       ['1st XI'],          'AVAILABLE',   { form: [22, 41, 5, 18, 9] }),
  mk('p4',  'Sam Whitford',     ['BWL'],        'RHB', 'FAST',              ['1st XI'],          'AVAILABLE',   { form: [4, 1, 12, 0, 6], note: '24 wkts @ 18.4' }),
  mk('p5',  'Ash Deluca',       ['BAT'],        'RHB', 'LEG_SPIN',          ['1st XI'],          'MAYBE',       { note: 'Work — confirm Fri' }),
  mk('p6',  'Nathan Cole',      ['ALL'],        'RHB', 'OFF_SPIN',          ['1st XI','2nd XI'], 'AVAILABLE',   { form: [18, 62, 31, 7, 25] }),
  mk('p7',  'Marcus Webb',      ['BWL'],        'LHB', 'LEFT_ARM_ORTHODOX', ['1st XI'],          'AVAILABLE',   { form: [2, 0, 8, 11, 3] }),
  mk('p8',  'Dylan Hartley',    ['BAT'],        'RHB', 'NONE',              ['1st XI'],          'UNAVAILABLE', { note: 'Away — wedding' }),
  mk('p9',  'Ben Forsyth',      ['ALL'],        'RHB', 'MEDIUM',            ['1st XI','2nd XI'], 'AVAILABLE',   { form: [40, 12, 55, 19, 8] }),
  mk('p10', 'Cooper Nguyen',    ['WKT','BAT'],  'RHB', 'NONE',              ['1st XI'],          'NO_RESPONSE', {}),
  mk('p11', 'Liam Okafor',      ['BWL'],        'RHB', 'FAST',              ['1st XI'],          'AVAILABLE',   { form: [0, 5, 1, 0, 2], note: '19 wkts @ 21.0' }),
  mk('p12', 'Harrison Reid',    ['BAT'],        'RHB', 'NONE',              ['1st XI','2nd XI'], 'MAYBE',       { note: 'Niggle — fitness test' }),
  mk('p13', 'Oscar Mendel',     ['ALL'],        'LHB', 'OFF_SPIN',          ['1st XI'],          'AVAILABLE',   { form: [28, 9, 16, 44, 21] }),
  mk('p14', 'Joe Castellano',   ['BWL'],        'RHB', 'FAST_MEDIUM',       ['2nd XI'],          'AVAILABLE',   { clash: '2nd XI' }),
  mk('p15', 'Aaron Pillai',     ['BAT'],        'RHB', 'NONE',              ['2nd XI'],          'AVAILABLE',   { clash: '2nd XI' }),
  mk('p16', 'Findlay Grewar',   ['BAT'],        'LHB', 'LEG_SPIN',          ['1st XI'],          'NO_RESPONSE', {}),
  mk('p17', 'Zane Mitchell',    ['ALL'],        'RHB', 'MEDIUM',            ['2nd XI'],          'AVAILABLE',   {}),
  mk('p18', 'Patrick Shaw',     ['WKT'],        'RHB', 'NONE',              ['2nd XI'],          'MAYBE',       {}),
  mk('p19', 'Hugo Bennett',     ['BWL'],        'RHB', 'OFF_SPIN',          ['2nd XI'],          'AVAILABLE',   {}),
  mk('p20', 'Eli Rosenthal',    ['BAT'],        'RHB', 'NONE',              ['2nd XI'],          'UNAVAILABLE', { note: 'Injured — hamstring' }),
  mk('p21', 'Curtis Hale',      ['ALL'],        'RHB', 'FAST_MEDIUM',       ['1st XI'],          'AVAILABLE',   { form: [11, 33, 6, 29, 15] }),
  mk('p22', 'Wesley Tran',      ['BAT'],        'RHB', 'NONE',              ['Veterans'],        'AVAILABLE',   { dormant: true, note: 'Last played 2023' }),
  mk('p23', 'George Ngata',     ['BWL'],        'LHB', 'LEFT_ARM_ORTHODOX', ['Veterans'],        'NO_RESPONSE', { dormant: true }),
  mk('p24', 'Isaac Valentine',  ['BAT','WKT'],  'RHB', 'NONE',              ['2nd XI'],          'AVAILABLE',   {}),
];

// A sensible pre-filled XI for the selection boards (batting order).
const BS_DEFAULT_XI = ['p1','p2','p3','p6','p13','p9','p10','p4','p11','p7','p21'];

// Last round's named XI (drives "autofill from last week"). Note p8 Dylan
// Hartley played last week but is now unavailable — so autofill skips him and
// falls back to the best available player.
const BS_PREV_XI = ['p1','p2','p3','p6','p13','p9','p10','p4','p11','p7','p8'];

// Roster availability tallies for the at-a-glance bar.
function bsTally(players) {
  const t = { AVAILABLE: 0, MAYBE: 0, NO_RESPONSE: 0, UNAVAILABLE: 0 };
  players.forEach(p => { t[p.avail] = (t[p.avail] || 0) + 1; });
  return t;
}

// Squads (selection pools). Players are assigned to one for selection.
const BS_SQUADS = ['1st XI', '2nd XI', '3rd XI', '4th XI', 'Veterans'];

Object.assign(window, {
  BS_AVAIL, BS_AVAIL_ORDER, BS_ROLES, BS_BOWL, BS_CLUB, BS_SQUADS,
  BS_FIXTURE, BS_DATES, BS_PLAYERS, BS_DEFAULT_XI, BS_PREV_XI, bsTally,
});
