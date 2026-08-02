// BetterClubManager redesign — fixture data + the pure model/rules engine.
//
// This is a faithful React port of the reference prototype
// (docs/design_handoff_clubmanager_redesign/BetterClubManager Redesign.dc.html).
// Everything here is client-side scaffolding: the fixture names, dates and
// dollar amounts are placeholders written to make the rules and relationships
// visible, exactly as the handoff describes. The real build swaps these for the
// schema + endpoints in the "Data model & API" section of the handoff README.
//
// Nothing in this file renders. It holds the seed data and the derived-on-read
// computations (roster rules, diary critical path, qualification status,
// booking conflicts) that every screen reads.

// ── Week ────────────────────────────────────────────────────────────────────
export const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
export const DATES = ['3 Nov', '4 Nov', '5 Nov', '6 Nov', '7 Nov', '8 Nov', '9 Nov']

// ── Operational areas ───────────────────────────────────────────────────────
// A slice of club work with its own weekly shift pattern, the role that covers
// it, and the qualification that gates it (null = ungated).
export const AREAS = {
  bar:     { name: 'Bar',        dept: 'Food & Beverage',    color: '#f5b542', role: 'Bar Supervisor', qual: 'RSA' },
  kitchen: { name: 'Kitchen',    dept: 'Food & Beverage',    color: '#f97316', role: 'Canteen',        qual: 'Food Handling' },
  umpire:  { name: 'Umpires',    dept: 'Cricket Operations', color: '#3b82f6', role: 'Umpire',         qual: 'Umpire Accreditation' },
  scorer:  { name: 'Scorer',     dept: 'Cricket Operations', color: '#06b6d4', role: 'Scorer',         qual: null },
  ground:  { name: 'Groundsman', dept: 'Cricket Operations', color: '#16c784', role: 'Groundsman',     qual: null },
  train:   { name: 'Training',   dept: 'Cricket Operations', color: '#a855f7', role: 'Coach',          qual: 'Working With Children' },
}

// The repeating weekly template: [areaKey, dayIndex, startHour, endHour, headcount]
export const SHIFT_DEFS = [
  ['bar', 1, 17, 21, 1], ['bar', 3, 17, 22, 2], ['bar', 4, 17, 20, 1], ['bar', 5, 12, 24, 2], ['bar', 6, 12, 24, 2],
  ['kitchen', 1, 18, 20, 1], ['kitchen', 3, 18, 20, 2], ['kitchen', 4, 18, 20, 1], ['kitchen', 5, 18, 20, 1], ['kitchen', 6, 16, 20, 1],
  ['umpire', 5, 12, 18.5, 4], ['umpire', 6, 12, 18.5, 4],
  ['scorer', 5, 12, 18.5, 4], ['scorer', 6, 12, 18.5, 4],
  ['ground', 0, 12, 15, 1], ['ground', 2, 12, 15, 1], ['ground', 5, 9, 10, 1], ['ground', 6, 9, 10, 1],
  ['train', 1, 16.5, 18.5, 2], ['train', 3, 16.5, 18.5, 2],
]

// ── People (roster/volunteer view) ──────────────────────────────────────────
export const PEOPLE = [
  { id: 'p1',  name: 'Andrew Pearce',   roles: ['Bar Supervisor'],           quals: ['RSA'],                               days: [1, 3, 4, 5, 6], max: 3, family: 'Pearce',    hoursYtd: 42 },
  { id: 'p2',  name: 'Sarah Whitcombe', roles: ['Scorer', 'Team Manager'],   quals: ['Working With Children'],             days: [5, 6],          max: 3, family: 'Whitcombe', hoursYtd: 28 },
  { id: 'p3',  name: 'Dev Patel',       roles: ['Groundsman'],               quals: [],                                    days: [0, 2, 5],       max: 4, family: 'Patel',     hoursYtd: 11 },
  { id: 'p4',  name: 'Megan Doyle',     roles: ['Canteen', 'Bar Supervisor'], quals: ['RSA', 'Food Handling'],             days: [3, 4, 5, 6],    max: 3, family: 'Doyle',     hoursYtd: 63 },
  { id: 'p5',  name: 'Tom Ellery',      roles: ['Umpire'],                   quals: ['Umpire Accreditation'],              days: [5, 6],          max: 2, family: 'Ellery',    hoursYtd: 19 },
  { id: 'p6',  name: 'Priya Raman',     roles: ['Scorer'],                   quals: [],                                    days: [5, 6],          max: 3, family: 'Raman',     hoursYtd: 24 },
  { id: 'p7',  name: 'Cal Doyle',       roles: ['Coach', 'Umpire'],          quals: ['Working With Children'],             days: [1, 3, 5],       max: 3, family: 'Doyle',     hoursYtd: 31, playsSat: true },
  { id: 'p8',  name: 'Nick Bramley',    roles: ['Bar Supervisor', 'Canteen'], quals: ['RSA', 'Food Handling'],             days: [1, 3, 4, 5, 6], max: 4, family: 'Bramley',   hoursYtd: 8 },
  { id: 'p9',  name: 'Helen Vaughan',   roles: ['Canteen'],                  quals: ['Food Handling'],                     days: [1, 3, 4, 6],    max: 3, family: 'Vaughan',   hoursYtd: 37 },
  { id: 'p10', name: 'Rob Kinsella',    roles: ['Umpire', 'Groundsman'],     quals: ['Umpire Accreditation'],              days: [0, 2, 5, 6],    max: 4, family: 'Kinsella',  hoursYtd: 55 },
  { id: 'p11', name: 'Aisha Nasser',    roles: ['Coach'],                    quals: ['Working With Children', 'First Aid'], days: [1, 3],         max: 2, family: 'Nasser',    hoursYtd: 16 },
  { id: 'p12', name: 'Grant Whitcombe', roles: ['Umpire', 'Scorer'],         quals: ['Umpire Accreditation'],              days: [5, 6],          max: 3, family: 'Whitcombe', hoursYtd: 21 },
]

export const QUAL_STATUS = { 'RSA': 'expired', 'Umpire Accreditation': 'ok', 'Working With Children': 'ok', 'Food Handling': 'ok', 'First Aid': 'soon' }

// The rostering rules, in the order they read in the side panel.
export const RULES = [
  { label: 'Required role and qualification for the area', tone: 'block' },
  { label: 'Volunteer availability (declared days)', tone: 'block' },
  { label: 'No overlapping shifts on the same day', tone: 'block' },
  { label: 'Max shifts per person per week', tone: 'warn' },
  { label: 'Fair spread — flags over-rostered people', tone: 'warn' },
  { label: 'Clash with a match they are selected in (BetterSelect)', tone: 'warn' },
  { label: 'Two people from one family on the same slot', tone: 'warn' },
]

// ── Formatting helpers ──────────────────────────────────────────────────────
export function fmtHour(h) {
  const hh = Math.floor(h)
  const mm = Math.round((h - hh) * 60)
  if (hh === 24) return '12am'
  const ampm = hh >= 12 && hh < 24 ? 'pm' : 'am'
  let base = hh % 12
  if (base === 0) base = 12
  return base + (mm ? ':' + String(mm).padStart(2, '0') : '') + ampm
}
export function initialsOf(name) { return name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase() }
export function money(n) { return '$' + n.toLocaleString('en-AU') }

// ── Roster: build the seeded half-filled week a secretary actually opens ─────
export function buildSlots() {
  const slots = []
  let i = 0
  SHIFT_DEFS.forEach(([area, day, start, end, count]) => {
    for (let k = 0; k < count; k++) slots.push({ id: 's' + (i++), area, day, start, end, assignee: null, warns: [] })
  })
  const seed = [
    ['bar', 1, 'p1'], ['bar', 3, 'p8'], ['bar', 5, 'p4'], ['kitchen', 3, 'p9'], ['kitchen', 6, 'p9'],
    ['umpire', 5, 'p5'], ['umpire', 5, 'p10'], ['scorer', 5, 'p2'], ['scorer', 6, 'p6'],
    ['ground', 0, 'p3'], ['ground', 2, 'p3'], ['train', 1, 'p11'], ['train', 3, 'p11'],
  ]
  seed.forEach(([area, day, pid]) => {
    const s = slots.find(x => x.area === area && x.day === day && !x.assignee)
    if (s) s.assignee = pid
  })
  return slots
}

export function personById(id) { return PEOPLE.find(p => p.id === id) }

// ── Roster rules engine ─────────────────────────────────────────────────────
// Returns { blocks: [], warns: [] } for putting `slot` on `person`. Honours the
// two configurable settings: enforceQualifications (hard block vs warn) and
// weeklyShiftCap (club-wide override of per-person caps; 0 = use each person's).
export function checkAssign(person, slot, slots, opts = {}) {
  const blocks = []
  const warns = []
  const a = AREAS[slot.area]
  const cap = opts.weeklyShiftCap || person.max
  if (a.qual && !person.quals.includes(a.qual)) {
    (opts.enforceQualifications === false ? warns : blocks).push('No ' + a.qual)
  }
  if (!person.days.includes(slot.day)) blocks.push('Not available ' + DOW[slot.day])
  const mine = slots.filter(s => s.assignee === person.id && s.id !== slot.id)
  if (mine.some(s => s.day === slot.day && s.start < slot.end && slot.start < s.end)) blocks.push('Overlaps another shift')
  if (!person.roles.includes(a.role)) warns.push('Not in the ' + a.role + ' role')
  if (mine.length + 1 > cap) warns.push('Over their ' + cap + '-shift weekly cap')
  if (mine.length + 1 >= 4) warns.push('Heavy week — spread the load')
  if (person.playsSat && slot.day === 5 && slot.start < 18.5) warns.push('Selected to play Saturday in BetterSelect')
  if (slots.some(s => s.assignee && s.id !== slot.id && s.day === slot.day && s.area === slot.area
    && s.start === slot.start && personById(s.assignee) && personById(s.assignee).family === person.family)) {
    warns.push('Same family already on this slot')
  }
  return { blocks, warns }
}

// Rank all volunteers for a slot: no blocking violation, prefer zero warnings,
// break ties on current load (fairness).
export function bestFor(slot, slots, opts) {
  const scored = PEOPLE.map(p => {
    const res = checkAssign(p, slot, slots, opts)
    const load = slots.filter(s => s.assignee === p.id).length
    return { p, res, load, score: res.blocks.length * 100 + res.warns.length * 10 + load }
  }).filter(x => x.res.blocks.length === 0)
  scored.sort((a, b) => a.score - b.score)
  return scored
}

// ── Club Diary ──────────────────────────────────────────────────────────────
// Season 2026/27 runs 1 Jul 2026 → 30 Jun 2027. "Today" is 3 Nov 2026 (day 125).
export const SEASON_START = Date.UTC(2026, 6, 1)
export const SEASON_DAYS = 365
export const TODAY_DAY = 125

export const MONTH_DEFS = [
  ['JUL', 31], ['AUG', 31], ['SEP', 30], ['OCT', 31], ['NOV', 30], ['DEC', 31],
  ['JAN', 31], ['FEB', 28], ['MAR', 31], ['APR', 30], ['MAY', 31], ['JUN', 30],
]

export function dayOf(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return Math.round((Date.UTC(y, m - 1, d) - SEASON_START) / 86400000)
}
export function fmtDate(iso) {
  const [, m, d] = iso.split('-').map(Number)
  return d + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]
}

export const CADENCES = ['Annual', 'One-Time', 'Quarterly', 'Monthly', 'Weekly', 'Conditional']

export const DIARY_TASKS = [
  { id: 'fin', title: 'Annual financial report & audit', cadence: 'Annual', role: 'Treasurer', person: 'Marcus Reid', start: '2026-07-06', due: '2026-08-07', budget: 1800, spent: 1800, state: 'done', deps: [] },
  { id: 'ins', title: 'Insurance renewal', cadence: 'Annual', role: 'Treasurer', person: 'Marcus Reid', start: '2026-07-13', due: '2026-07-31', budget: 3800, spent: 3800, state: 'done', deps: [] },
  { id: 'fees', title: 'Set season fee schedule', cadence: 'Annual', role: 'Treasurer', person: 'Marcus Reid', start: '2026-08-03', due: '2026-08-21', budget: 0, spent: 0, state: 'done', deps: ['fin'] },
  { id: 'agm', title: 'AGM — notice, papers, meeting', cadence: 'Annual', role: 'Secretary', person: 'Jane Halloran', start: '2026-08-03', due: '2026-08-26', budget: 350, spent: 410, state: 'done', deps: ['fin'] },
  { id: 'affil', title: 'Association affiliation fees', cadence: 'Annual', role: 'Treasurer', person: 'Marcus Reid', start: '2026-08-10', due: '2026-08-28', budget: 2400, spent: 2400, state: 'done', deps: ['fin'] },
  { id: 'noms', title: 'Team nominations to association', cadence: 'Annual', role: 'Junior Coordinator', person: 'Cal Doyle', start: '2026-08-10', due: '2026-08-31', budget: 0, spent: 0, state: 'done', deps: ['agm'] },
  { id: 'equip', title: 'Equipment audit & season order', cadence: 'Annual', role: 'Equipment Officer', person: 'Nick Bramley', start: '2026-08-17', due: '2026-09-18', budget: 5200, spent: 4870, state: 'done', deps: ['fees'] },
  { id: 'reg', title: 'Player registrations open', cadence: 'Annual', role: 'Registrar', person: 'Priya Raman', start: '2026-09-07', due: '2026-09-30', budget: 0, spent: 0, state: 'done', deps: ['fees', 'noms'] },
  { id: 'fixt', title: 'Fixture upload & ground allocation', cadence: 'Annual', role: 'Cricket Operations', person: 'Grant Whitcombe', start: '2026-09-14', due: '2026-10-02', budget: 0, spent: 0, state: 'done', deps: ['noms'] },
  { id: 'bee', title: 'Pre-season working bee — ground prep', cadence: 'Annual', role: 'Ground Manager', person: 'Dev Patel', start: '2026-09-19', due: '2026-10-03', budget: 400, spent: 385, state: 'done', deps: [] },
  { id: 'signon', title: 'Junior sign-on day', cadence: 'One-Time', role: 'Junior Coordinator', person: 'Cal Doyle', start: '2026-09-26', due: '2026-10-04', budget: 600, spent: 540, state: 'done', deps: ['reg'] },
  { id: 'r1', title: 'Round 1 — first match day', cadence: 'One-Time', role: 'Cricket Operations', person: 'Grant Whitcombe', start: '2026-10-10', due: '2026-10-11', budget: 0, spent: 0, state: 'done', milestone: true, deps: ['fixt', 'reg', 'bee', 'equip'] },
  { id: 'cond', title: 'Facilities condition report', cadence: 'Annual', role: 'Ground Manager', person: 'Dev Patel', start: '2026-09-01', due: '2026-09-18', budget: 0, spent: 0, state: 'open', deps: [] },
  { id: 'licence', title: 'Liquor licence renewal', cadence: 'Annual', role: 'Bar Manager', person: 'Andrew Pearce', start: '2026-09-01', due: '2026-09-25', budget: 780, spent: 0, state: 'open', deps: [] },
  { id: 'compl', title: 'WWCC & accreditation compliance sweep', cadence: 'Annual', role: 'Secretary', person: 'Jane Halloran', start: '2026-09-07', due: '2026-10-02', budget: 0, spent: 0, state: 'open', deps: [] },
  { id: 'grant', title: 'Facilities grant application', cadence: 'Annual', role: 'President', person: 'Helen Vaughan', start: '2026-10-05', due: '2026-11-27', budget: 0, spent: 0, state: 'open', deps: ['cond'] },
  { id: 'carn', title: 'Christmas carnival', cadence: 'One-Time', role: 'Social Coordinator', person: 'Megan Doyle', start: '2026-10-20', due: '2026-12-12', budget: 1900, spent: 240, state: 'open', deps: [] },
  { id: 'elig', title: 'Finals eligibility audit', cadence: 'Annual', role: 'Registrar', person: 'Priya Raman', start: '2027-01-04', due: '2027-01-24', budget: 0, spent: 0, state: 'open', deps: ['reg'] },
  { id: 'life', title: 'Life membership nominations', cadence: 'Annual', role: 'Secretary', person: 'Jane Halloran', start: '2027-02-01', due: '2027-02-21', budget: 0, spent: 0, state: 'open', deps: [] },
  { id: 'pres', title: 'Presentation night', cadence: 'Annual', role: 'Social Coordinator', person: 'Megan Doyle', start: '2027-02-01', due: '2027-03-27', budget: 4200, spent: 0, state: 'open', deps: [] },
  { id: 'renov', title: 'Turf wicket renovation', cadence: 'Annual', role: 'Ground Manager', person: 'Dev Patel', start: '2027-04-05', due: '2027-06-25', budget: 6500, spent: 0, state: 'open', deps: ['cond'] },
  { id: 'acquit', title: 'Facilities grant acquittal', cadence: 'Annual', role: 'Treasurer', person: 'Marcus Reid', start: '2027-05-01', due: '2027-06-30', budget: 0, spent: 0, state: 'open', deps: ['grant'] },
  { id: 'bas', title: 'BAS lodgement', cadence: 'Quarterly', role: 'Treasurer', person: 'Marcus Reid', start: '2026-07-01', due: '2027-06-30', budget: 0, spent: 0, state: 'recurring', rule: '28th of Oct, Jan, Apr, Jul', deps: [] },
  { id: 'cmte', title: 'Committee meeting', cadence: 'Monthly', role: 'Secretary', person: 'Jane Halloran', start: '2026-07-01', due: '2027-06-30', budget: 0, spent: 0, state: 'recurring', rule: 'First Tuesday, agenda out 7 days prior', deps: [] },
  { id: 'stock', title: 'Bar stocktake', cadence: 'Monthly', role: 'Bar Manager', person: 'Andrew Pearce', start: '2026-09-01', due: '2027-03-31', budget: 0, spent: 0, state: 'recurring', rule: 'Last Sunday, in season only', deps: [] },
  { id: 'bank', title: 'Banking & takings reconciliation', cadence: 'Weekly', role: 'Treasurer', person: 'Marcus Reid', start: '2026-09-01', due: '2027-03-31', budget: 0, spent: 0, state: 'recurring', rule: 'Monday, in season only', deps: [] },
  { id: 'wet', title: 'Wet weather ground inspection', cadence: 'Conditional', role: 'Ground Manager', person: 'Dev Patel', start: '2026-10-01', due: '2027-03-31', budget: 0, spent: 0, state: 'conditional', rule: 'Trigger: >10mm rain in the 24h before a match', deps: [] },
  { id: 'incid', title: 'Incident report follow-up', cadence: 'Conditional', role: 'Secretary', person: 'Jane Halloran', start: '2026-09-01', due: '2027-03-31', budget: 0, spent: 0, state: 'conditional', rule: 'Trigger: within 48h of a reported incident', deps: [] },
]

export const DIARY_TEMPLATES = [
  { title: 'Annual financial report & audit', cadence: 'Annual', role: 'Treasurer', timing: 'Starts 1 Jul · due 5 weeks later', budget: 1800, deps: 0 },
  { title: 'Insurance renewal', cadence: 'Annual', role: 'Treasurer', timing: 'Due 30 days before season start', budget: 3800, deps: 0 },
  { title: 'AGM — notice, papers, meeting', cadence: 'Annual', role: 'Secretary', timing: 'Due 8 weeks before Round 1', budget: 350, deps: 1 },
  { title: 'Set season fee schedule', cadence: 'Annual', role: 'Treasurer', timing: 'Due 7 weeks before Round 1', budget: 0, deps: 1 },
  { title: 'Team nominations to association', cadence: 'Annual', role: 'Junior Coordinator', timing: 'Due 6 weeks before Round 1', budget: 0, deps: 1 },
  { title: 'Equipment audit & season order', cadence: 'Annual', role: 'Equipment Officer', timing: 'Due 3 weeks before Round 1', budget: 5200, deps: 1 },
  { title: 'Facilities condition report', cadence: 'Annual', role: 'Ground Manager', timing: 'Due 3 weeks before Round 1', budget: 0, deps: 0 },
  { title: 'Liquor licence renewal', cadence: 'Annual', role: 'Bar Manager', timing: 'Due 2 weeks before Round 1', budget: 780, deps: 0 },
  { title: 'Fixture upload & ground allocation', cadence: 'Annual', role: 'Cricket Operations', timing: 'Due 1 week before Round 1', budget: 0, deps: 1 },
  { title: 'Junior sign-on day', cadence: 'One-Time', role: 'Junior Coordinator', timing: 'Due 1 week before Round 1', budget: 600, deps: 1 },
  { title: 'Facilities grant application', cadence: 'Annual', role: 'President', timing: 'Opens at Round 1 · due 8 weeks later', budget: 0, deps: 1 },
  { title: 'Presentation night', cadence: 'Annual', role: 'Social Coordinator', timing: 'Due in the 2 weeks after the last round', budget: 4200, deps: 0 },
  { title: 'Turf wicket renovation', cadence: 'Annual', role: 'Ground Manager', timing: 'Starts 1 week after the last round', budget: 6500, deps: 1 },
  { title: 'Facilities grant acquittal', cadence: 'Annual', role: 'Treasurer', timing: 'Due 30 Jun', budget: 0, deps: 1 },
  { title: 'BAS lodgement', cadence: 'Quarterly', role: 'Treasurer', timing: '28th of Oct, Jan, Apr, Jul', budget: 0, deps: 0 },
  { title: 'Committee meeting', cadence: 'Monthly', role: 'Secretary', timing: 'First Tuesday, agenda out 7 days prior', budget: 0, deps: 0 },
  { title: 'Bar stocktake', cadence: 'Monthly', role: 'Bar Manager', timing: 'Last Sunday, in season only', budget: 0, deps: 0 },
  { title: 'Banking & takings reconciliation', cadence: 'Weekly', role: 'Treasurer', timing: 'Monday, in season only', budget: 0, deps: 0 },
  { title: 'Wet weather ground inspection', cadence: 'Conditional', role: 'Ground Manager', timing: 'Trigger: >10mm rain in the 24h before a match', budget: 0, deps: 0 },
  { title: 'Incident report follow-up', cadence: 'Conditional', role: 'Secretary', timing: 'Trigger: within 48h of a reported incident', budget: 0, deps: 0 },
]

export const ROLE_HOLDERS = [
  { role: 'President', person: 'Helen Vaughan' },
  { role: 'Secretary', person: 'Jane Halloran' },
  { role: 'Treasurer', person: 'Marcus Reid' },
  { role: 'Junior Coordinator', person: 'Cal Doyle' },
  { role: 'Ground Manager', person: 'Dev Patel' },
  { role: 'Bar Manager', person: 'Andrew Pearce' },
  { role: 'Registrar', person: 'Priya Raman' },
  { role: 'Cricket Operations', person: 'Grant Whitcombe' },
  { role: 'Equipment Officer', person: 'Nick Bramley' },
  { role: 'Social Coordinator', person: 'Megan Doyle' },
]

// status → { fg, label } for the diary timeline tones.
export const DIARY_TONE = {
  done:        { fg: '#16c784', label: 'DONE' },
  open:        { fg: '#6366F1', label: 'IN PROGRESS' },
  overdue:     { fg: '#ef5b5b', label: 'OVERDUE' },
  blocked:     { fg: '#ef5b5b', label: 'BLOCKED' },
  upcoming:    { fg: '#5b6072', label: 'NOT STARTED' },
  milestone:   { fg: '#a855f7', label: 'MILESTONE' },
  recurring:   { fg: '#06b6d4', label: 'RECURS' },
  conditional: { fg: '#f5b542', label: 'ON TRIGGER' },
}

// Derive every diary task's live status, the critical path (longest dependency
// chain through remaining work) and the dependents map. Nothing here is stored.
export function diaryModel() {
  const byId = {}
  DIARY_TASKS.forEach(t => { byId[t.id] = t })

  const resolved = DIARY_TASKS.map(t => {
    const s = dayOf(t.start)
    const d = dayOf(t.due)
    const blockers = t.deps.filter(id => byId[id].state !== 'done')
    let status = t.state
    if (t.state === 'done') status = 'done'
    else if (t.state === 'recurring' || t.state === 'conditional') status = t.state
    else if (blockers.length) status = 'blocked'
    else if (d < TODAY_DAY) status = 'overdue'
    else if (s <= TODAY_DAY) status = 'open'
    else status = 'upcoming'
    if (t.milestone && status === 'done') status = 'milestone'
    return { ...t, startDay: s, dueDay: d, dur: Math.max(1, d - s), blockers, status }
  })
  const rById = {}
  resolved.forEach(t => { rById[t.id] = t })

  const dated = resolved.filter(t => t.state !== 'recurring' && t.state !== 'conditional')
  const memo = {}
  function chain(id) {
    if (memo[id]) return memo[id]
    const t = rById[id]
    const live = t.deps.filter(d => rById[d] && rById[d].state !== 'done')
    let best = { len: t.dur, path: [id] }
    live.forEach(d => {
      const c = chain(d)
      if (c.len + t.dur > best.len) best = { len: c.len + t.dur, path: c.path.concat([id]) }
    })
    memo[id] = best
    return best
  }
  let cp = { len: 0, path: [] }
  dated.filter(t => t.state !== 'done').forEach(t => { const c = chain(t.id); if (c.len > cp.len) cp = c })
  const cpSet = {}
  cp.path.forEach(id => { cpSet[id] = true })

  const dependents = {}
  resolved.forEach(t => t.deps.forEach(d => { (dependents[d] = dependents[d] || []).push(t.id) }))

  return { resolved, rById, cpSet, cpPath: cp.path, cpLen: cp.len, dependents }
}

// ── Directory (one record per person) ───────────────────────────────────────
export const DIR_TODAY = dayOf('2026-11-03')

export const DIRECTORY = [
  { id: 'p1', name: 'Andrew Pearce', since: '2019', email: 'a.pearce@example.com', phone: '0412 884 201', segs: ['Volunteer', 'Committee'], position: { title: 'Bar Manager', term: '2nd year · to Aug 2027' }, roles: ['Bar Supervisor'], interested: [], family: 'Pearce', quals: [{ name: 'RSA', expiry: '2026-05-14' }], hours: [['Bar shift', 26], ['Working bee', 9], ['Committee meeting', 7]] },
  { id: 'p2', name: 'Sarah Whitcombe', since: '2021', email: 's.whitcombe@example.com', phone: '0438 112 907', segs: ['Volunteer', 'Parent'], position: null, roles: ['Scorer', 'Team Manager'], interested: ['Canteen'], family: 'Whitcombe', quals: [{ name: 'Working With Children', expiry: '2027-08-22' }], hours: [['Scoring', 18], ['Junior coaching', 10]] },
  { id: 'p3', name: 'Dev Patel', since: '2017', email: 'd.patel@example.com', phone: '0401 556 330', segs: ['Volunteer', 'Committee'], position: { title: 'Ground Manager', term: '4th year · to Aug 2027' }, roles: ['Groundsman'], interested: ['BBQ'], family: 'Patel', quals: [{ name: 'Chemical Handling', expiry: '2028-03-01' }], hours: [['Wicket preparation', 41], ['Boundary line marking', 14], ['Working bee', 12]] },
  { id: 'p4', name: 'Megan Doyle', since: '2020', email: 'm.doyle@example.com', phone: '0427 690 118', segs: ['Volunteer', 'Committee', 'Parent'], position: { title: 'Social Coordinator', term: '1st year · to Aug 2027' }, roles: ['Canteen', 'Bar Supervisor'], interested: [], family: 'Doyle', quals: [{ name: 'RSA', expiry: '2027-11-30' }, { name: 'Food Handling', expiry: '2027-02-10' }], hours: [['Canteen shift', 38], ['Bar shift', 17], ['Committee meeting', 8]] },
  { id: 'p5', name: 'Tom Ellery', since: '2023', email: 't.ellery@example.com', phone: '0455 202 774', segs: ['Volunteer', 'Player'], position: null, roles: ['Umpire'], interested: [], family: 'Ellery', quals: [{ name: 'Umpire Accreditation', expiry: '2027-06-30' }], hours: [['Umpiring', 19]] },
  { id: 'p6', name: 'Priya Raman', since: '2022', email: 'p.raman@example.com', phone: '0466 341 552', segs: ['Volunteer', 'Committee'], position: { title: 'Registrar', term: '2nd year · to Aug 2027' }, roles: ['Scorer'], interested: ['Team Manager'], family: 'Raman', quals: [{ name: 'Working With Children', expiry: '2029-01-15' }], hours: [['Scoring', 16], ['Committee meeting', 8]] },
  { id: 'p7', name: 'Cal Doyle', since: '2018', email: 'c.doyle@example.com', phone: '0432 887 016', segs: ['Volunteer', 'Committee', 'Player', 'Parent'], position: { title: 'Junior Coordinator', term: '3rd year · to Aug 2027' }, roles: ['Coach', 'Umpire'], interested: [], family: 'Doyle', quals: [{ name: 'Working With Children', expiry: '2028-04-04' }, { name: 'Level 1 Coaching', expiry: '2026-12-20' }], hours: [['Junior coaching', 22], ['Committee meeting', 9]] },
  { id: 'p8', name: 'Nick Bramley', since: '2024', email: 'n.bramley@example.com', phone: '0413 775 289', segs: ['Volunteer', 'Committee'], position: { title: 'Equipment Officer', term: '1st year · to Aug 2027' }, roles: ['Bar Supervisor', 'Canteen'], interested: [], family: 'Bramley', quals: [{ name: 'RSA', expiry: '2028-09-09' }, { name: 'Food Handling', expiry: '2026-12-31' }], hours: [['Bar shift', 8]] },
  { id: 'p9', name: 'Helen Vaughan', since: '2014', email: 'h.vaughan@example.com', phone: '0407 118 664', segs: ['Volunteer', 'Committee'], position: { title: 'President', term: '2nd year · to Aug 2027' }, roles: ['Canteen'], interested: [], family: 'Vaughan', quals: [{ name: 'Food Handling', expiry: '2027-05-19' }], hours: [['Canteen shift', 24], ['Committee meeting', 13]] },
  { id: 'p10', name: 'Rob Kinsella', since: '2016', email: 'r.kinsella@example.com', phone: '0421 903 447', segs: ['Volunteer'], position: null, roles: ['Umpire', 'Groundsman'], interested: [], family: 'Kinsella', quals: [{ name: 'Umpire Accreditation', expiry: '2026-12-15' }], hours: [['Umpiring', 31], ['Wicket preparation', 24]] },
  { id: 'p11', name: 'Aisha Nasser', since: '2025', email: 'a.nasser@example.com', phone: '0448 226 913', segs: ['Volunteer', 'Parent'], position: null, roles: ['Coach'], interested: ['Team Manager'], family: 'Nasser', quals: [{ name: 'Working With Children', expiry: '2029-07-01' }, { name: 'First Aid', expiry: '2026-12-28' }], hours: [['Junior coaching', 16]] },
  { id: 'p12', name: 'Grant Whitcombe', since: '2021', email: 'g.whitcombe@example.com', phone: '0439 550 872', segs: ['Volunteer', 'Committee', 'Parent'], position: { title: 'Cricket Operations', term: '2nd year · to Aug 2027' }, roles: ['Umpire', 'Scorer'], interested: [], family: 'Whitcombe', quals: [{ name: 'Umpire Accreditation', expiry: '2027-09-30' }], hours: [['Umpiring', 14], ['Scoring', 7]] },
  { id: 'p13', name: 'Marcus Reid', since: '2015', email: 'm.reid@example.com', phone: '0409 664 122', segs: ['Committee'], position: { title: 'Treasurer', term: '5th year · to Aug 2027' }, roles: [], interested: [], family: 'Reid', quals: [], hours: [['Committee meeting', 14], ['Banking', 22]] },
  { id: 'p14', name: 'Jane Halloran', since: '2013', email: 'j.halloran@example.com', phone: '0417 338 590', segs: ['Committee'], position: { title: 'Secretary', term: '6th year · to Aug 2027' }, roles: [], interested: ['Scorer'], family: 'Halloran', quals: [{ name: 'Working With Children', expiry: '2027-03-11' }], hours: [['Committee meeting', 15], ['Club admin', 29]] },
]

export const DIR_SEGS = ['All', 'Committee', 'Volunteer', 'Parent', 'Player']

export function qualState(expiry) {
  const d = dayOf(expiry)
  if (d < DIR_TODAY) return { key: 'expired', label: 'EXPIRED', fg: '#ef5b5b' }
  if (d - DIR_TODAY <= 60) return { key: 'soon', label: 'EXPIRES SOON', fg: '#f5b542' }
  return { key: 'current', label: 'CURRENT', fg: '#16c784' }
}

export function dirIdFor(name) {
  const p = DIRECTORY.find(x => x.name === name)
  return p ? p.id : null
}

// ── Facilities, bookings & assets ───────────────────────────────────────────
export const DAY_FROM = 8
export const DAY_TO = 24
export const DAY_SPAN = DAY_TO - DAY_FROM
export const FAC_ROW_H = 190       // ~11.9px per hour — a 2h booking clears its text
export const FAC_STACK_MIN = 26    // below this a block puts title and time on one line

export const FACILITIES = [
  { id: 'ground', name: 'Main Ground', kind: 'Turf oval · seats 400' },
  { id: 'wicket', name: 'Turf Wicket Block', kind: '4 strips · centre square' },
  { id: 'nets', name: 'Practice Nets', kind: '4 bays · synthetic' },
  { id: 'club', name: 'Clubrooms', kind: 'Bar + 120 standing' },
  { id: 'func', name: 'Function Room', kind: 'Seats 60 · hireable' },
]

export const SOURCES = {
  match:       { label: 'MATCH',    fg: '#6366F1' },
  training:    { label: 'TRAINING', fg: '#a855f7' },
  event:       { label: 'EVENT',    fg: '#f5b542' },
  hire:        { label: 'HIRE',     fg: '#06b6d4' },
  diary:       { label: 'DIARY',    fg: '#16c784' },
  maintenance: { label: 'MAINT',    fg: '#ef5b5b' },
}

export const BOOKINGS_SEED = [
  { id: 'b1', fac: 'ground', day: 5, start: 12, end: 18.5, title: '1st XI v Bayswater', src: 'match' },
  { id: 'b2', fac: 'ground', day: 6, start: 12, end: 18.5, title: '2nd XI v Gosnells', src: 'match' },
  { id: 'b3', fac: 'ground', day: 3, start: 17, end: 19, title: 'Junior training', src: 'training' },
  { id: 'b4', fac: 'wicket', day: 0, start: 12, end: 15, title: 'Wicket preparation', src: 'diary' },
  { id: 'b5', fac: 'wicket', day: 2, start: 12, end: 15, title: 'Wicket preparation', src: 'diary' },
  { id: 'b6', fac: 'wicket', day: 5, start: 9, end: 10, title: 'Match day prep', src: 'diary' },
  { id: 'b7', fac: 'nets', day: 1, start: 16.5, end: 18.5, title: 'Junior training', src: 'training' },
  { id: 'b8', fac: 'nets', day: 3, start: 16.5, end: 18.5, title: 'Junior training', src: 'training' },
  { id: 'b9', fac: 'nets', day: 4, start: 17, end: 19, title: 'Senior training', src: 'training' },
  { id: 'b10', fac: 'club', day: 5, start: 18, end: 23, title: 'Post-match function', src: 'event' },
  { id: 'b11', fac: 'club', day: 1, start: 19, end: 21, title: 'Committee meeting', src: 'diary' },
  { id: 'b12', fac: 'func', day: 4, start: 18, end: 23, title: 'Wellard 40th (external)', src: 'hire' },
  { id: 'b13', fac: 'func', day: 6, start: 10, end: 12, title: 'Junior presentation', src: 'event' },
]

export const REQUESTS_SEED = [
  { id: 'r1', fac: 'func', day: 5, start: 19, end: 23, title: 'Doyle engagement party', who: 'Megan Doyle', src: 'hire', note: 'Private hire · $180 room fee, bar staffed by club' },
  { id: 'r2', fac: 'nets', day: 3, start: 17, end: 19, title: 'Rep squad session', who: 'District coach (external)', src: 'training', note: 'Requested by association development officer' },
  { id: 'r3', fac: 'ground', day: 5, start: 9, end: 11.5, title: 'Come & try clinic', who: 'Cal Doyle', src: 'event', note: 'Under-9 recruitment · 30 kids expected' },
  { id: 'r4', fac: 'club', day: 1, start: 19, end: 21.5, title: 'Junior parents info night', who: 'Aisha Nasser', src: 'event', note: 'Needs projector and the small bar open' },
]

export const LOANS = [
  { id: 'l1', item: 'Bowling machine', to: 'Cal Doyle', out: '28 Oct', due: '4 Nov', overdue: false },
  { id: 'l2', item: 'Line marker + 4 paint drums', to: 'Dev Patel', out: '15 Sep', due: '22 Sep', overdue: true },
  { id: 'l3', item: 'Junior kit bag ×2', to: 'Aisha Nasser', out: '12 Oct', due: '30 Nov', overdue: false },
  { id: 'l4', item: "Scorer's tablet", to: 'Priya Raman', out: '2 Nov', due: '9 Nov', overdue: false },
  { id: 'l5', item: 'Portable nets (pair)', to: 'Rob Kinsella', out: '20 Oct', due: '1 Nov', overdue: true },
]

export const ASSETS = [
  { name: 'Junior kit bags', total: 8, out: 2, cond: 'Good' },
  { name: 'Senior kit bags', total: 4, out: 0, cond: 'Good' },
  { name: 'Bowling machines', total: 1, out: 1, cond: 'Serviced Sep' },
  { name: 'Portable nets', total: 3, out: 2, cond: 'One frame bent' },
  { name: 'Line markers', total: 2, out: 1, cond: 'Good' },
  { name: 'Scoring tablets', total: 3, out: 1, cond: 'Good' },
  { name: 'Covers (roll-on)', total: 2, out: 0, cond: 'Patch needed' },
]

export function overlaps(a, b) { return a.fac === b.fac && a.day === b.day && a.start < b.end && b.start < a.end }

// ── Committee ───────────────────────────────────────────────────────────────
export const POSITIONS = [
  { title: 'President', holder: 'Helen Vaughan', term: '2nd year · to Aug 2027', exec: true },
  { title: 'Vice President', holder: null, term: 'Vacant since Aug 2026', exec: true },
  { title: 'Secretary', holder: 'Jane Halloran', term: '6th year · to Aug 2027', exec: true },
  { title: 'Treasurer', holder: 'Marcus Reid', term: '5th year · to Aug 2027', exec: true },
  { title: 'Cricket Operations', holder: 'Grant Whitcombe', term: '2nd year · to Aug 2027' },
  { title: 'Junior Coordinator', holder: 'Cal Doyle', term: '3rd year · to Aug 2027' },
  { title: 'Ground Manager', holder: 'Dev Patel', term: '4th year · to Aug 2027' },
  { title: 'Bar Manager', holder: 'Andrew Pearce', term: '2nd year · to Aug 2027' },
  { title: 'Registrar', holder: 'Priya Raman', term: '2nd year · to Aug 2027' },
  { title: 'Equipment Officer', holder: 'Nick Bramley', term: '1st year · to Aug 2027' },
  { title: 'Social Coordinator', holder: 'Megan Doyle', term: '1st year · to Aug 2027' },
  { title: 'Volunteer Coordinator', holder: null, term: 'Never filled' },
]

export const MEETINGS = [
  { id: 'm6', kind: 'Special meeting', title: 'Grant application sign-off', date: '17 Nov 2026', status: 'scheduled',
    agenda: [
      { item: 'Facilities grant — scope and costings', who: 'Helen Vaughan', mins: 25, task: 'grant' },
      { item: 'Condition report findings', who: 'Dev Patel', mins: 15, task: 'cond' },
      { item: 'Co-contribution from reserves', who: 'Marcus Reid', mins: 20, task: null },
    ], present: [], apologies: [], motions: [], actions: [] },
  { id: 'm5', kind: 'Committee meeting', title: 'November meeting', date: '3 Nov 2026', status: 'today',
    agenda: [
      { item: 'Minutes of 6 Oct meeting', who: 'Jane Halloran', mins: 5, task: null },
      { item: "Treasurer's report + October takings", who: 'Marcus Reid', mins: 15, task: null },
      { item: 'Overdue: liquor licence renewal', who: 'Andrew Pearce', mins: 10, task: 'licence' },
      { item: 'Overdue: WWCC compliance sweep', who: 'Jane Halloran', mins: 10, task: 'compl' },
      { item: 'Volunteer Coordinator vacancy', who: 'Helen Vaughan', mins: 15, task: null },
      { item: 'Christmas carnival plan and budget', who: 'Megan Doyle', mins: 20, task: 'carn' },
    ], present: [], apologies: ['Nick Bramley'], motions: [], actions: [] },
  { id: 'm4', kind: 'Committee meeting', title: 'October meeting', date: '6 Oct 2026', status: 'held',
    agenda: [
      { item: 'Minutes of 1 Sep meeting', who: 'Jane Halloran', mins: 5, task: null },
      { item: 'Round 1 readiness', who: 'Grant Whitcombe', mins: 20, task: 'fixt' },
      { item: 'Equipment order variance', who: 'Nick Bramley', mins: 15, task: 'equip' },
      { item: 'Bar pricing for the season', who: 'Andrew Pearce', mins: 15, task: null },
    ],
    present: ['Helen Vaughan', 'Jane Halloran', 'Marcus Reid', 'Grant Whitcombe', 'Cal Doyle', 'Dev Patel', 'Andrew Pearce', 'Megan Doyle'],
    apologies: ['Priya Raman', 'Nick Bramley'],
    motions: [
      { title: 'That bar prices rise 50c per unit from Round 1', mover: 'Andrew Pearce', seconder: 'Marcus Reid', outcome: 'Carried', tally: '7 for, 1 against' },
      { title: 'That the equipment overspend of $330 be approved from contingency', mover: 'Nick Bramley', seconder: 'Helen Vaughan', outcome: 'Carried unanimously', tally: '8 for' },
    ],
    actions: [
      { what: 'Chase the liquor licence renewal with DLGSC', who: 'Andrew Pearce', due: '17 Oct 2026', state: 'overdue' },
      { what: 'Publish updated bar price list to the clubrooms', who: 'Andrew Pearce', due: '10 Oct 2026', state: 'done' },
      { what: 'Book the condition report inspector', who: 'Dev Patel', due: '20 Oct 2026', state: 'overdue' },
      { what: 'Draft the Christmas carnival budget', who: 'Megan Doyle', due: '3 Nov 2026', state: 'open' },
    ] },
  { id: 'm3', kind: 'Committee meeting', title: 'September meeting', date: '1 Sep 2026', status: 'held',
    agenda: [
      { item: 'Pre-season checklist', who: 'Helen Vaughan', mins: 20, task: null },
      { item: 'Team nominations confirmed', who: 'Cal Doyle', mins: 10, task: 'noms' },
      { item: 'Working bee date', who: 'Dev Patel', mins: 10, task: 'bee' },
    ],
    present: ['Helen Vaughan', 'Jane Halloran', 'Marcus Reid', 'Cal Doyle', 'Dev Patel', 'Priya Raman', 'Megan Doyle'],
    apologies: ['Andrew Pearce'],
    motions: [
      { title: 'That the working bee be held Saturday 19 September', mover: 'Dev Patel', seconder: 'Cal Doyle', outcome: 'Carried unanimously', tally: '7 for' },
    ],
    actions: [
      { what: 'Order line marking paint before the working bee', who: 'Dev Patel', due: '15 Sep 2026', state: 'done' },
      { what: 'Send working bee call-out to all families', who: 'Jane Halloran', due: '8 Sep 2026', state: 'done' },
    ] },
  { id: 'm2', kind: 'Annual General Meeting', title: 'AGM 2026', date: '26 Aug 2026', status: 'held',
    agenda: [
      { item: "President's report", who: 'Helen Vaughan', mins: 15, task: null },
      { item: 'Audited financial statements', who: 'Marcus Reid', mins: 20, task: 'fin' },
      { item: 'Election of office bearers', who: 'Jane Halloran', mins: 30, task: null },
      { item: 'Fee schedule for 2026/27', who: 'Marcus Reid', mins: 15, task: 'fees' },
    ],
    present: ['34 members present (quorum 20)'],
    apologies: ['11 apologies received'],
    motions: [
      { title: 'That the audited financial statements for 2025/26 be accepted', mover: 'Marcus Reid', seconder: 'Helen Vaughan', outcome: 'Carried unanimously', tally: '34 for' },
      { title: 'That senior fees be set at $340 and junior fees at $185', mover: 'Marcus Reid', seconder: 'Cal Doyle', outcome: 'Carried', tally: '29 for, 5 against' },
      { title: 'That the Vice President position remain open for casual appointment', mover: 'Helen Vaughan', seconder: 'Jane Halloran', outcome: 'Carried', tally: '31 for, 3 against' },
    ],
    actions: [
      { what: 'Lodge the annual return with the regulator', who: 'Jane Halloran', due: '30 Sep 2026', state: 'done' },
      { what: 'Publish the new fee schedule to the website', who: 'Priya Raman', due: '5 Sep 2026', state: 'done' },
      { what: 'Seek nominations for Vice President', who: 'Helen Vaughan', due: '31 Oct 2026', state: 'overdue' },
    ] },
]

export const CTE_STATUS = {
  today:     { label: 'TODAY', fg: '#6366F1' },
  scheduled: { label: 'SCHEDULED', fg: '#8a90a2' },
  held:      { label: 'MINUTES APPROVED', fg: '#16c784' },
}
export const ACTION_STATE = {
  done:    { label: 'DONE', fg: '#16c784' },
  open:    { label: 'OPEN', fg: '#6366F1' },
  overdue: { label: 'OVERDUE', fg: '#ef5b5b' },
}

// ── Events & ticketing ──────────────────────────────────────────────────────
export const EVENTS = [
  { id: 'e1', title: 'Come & try clinic', when: 'Sat 7 Nov 2026 · 9:00–11:30am', venue: 'Main Ground', status: 'open', kind: 'Free registration', cap: 30, budget: 0, task: null,
    tickets: [{ name: 'Junior participant', price: 0, sold: 18, qty: 30 }],
    needs: 'Needs 2 coaches + 1 first aid · 3 rostered',
    attendees: [
      { name: 'Ava Nasser', type: 'Junior participant', paid: 'FREE', note: 'Parent: Aisha Nasser' },
      { name: 'Ben Whitcombe', type: 'Junior participant', paid: 'FREE', note: 'Parent: Sarah Whitcombe' },
      { name: 'Charlie Doyle', type: 'Junior participant', paid: 'FREE', note: 'Parent: Megan Doyle' },
      { name: 'Dylan Pearce', type: 'Junior participant', paid: 'FREE', note: 'New family' },
      { name: 'Ella Kinsella', type: 'Junior participant', paid: 'FREE', note: 'Parent: Rob Kinsella' },
      { name: '+ 13 more registrations', type: '', paid: '', note: '' },
    ] },
  { id: 'e2', title: 'Junior presentation', when: 'Sun 8 Nov 2026 · 10:00am–12:00pm', venue: 'Function Room', status: 'open', kind: 'RSVP', cap: 60, budget: 0, task: null,
    tickets: [{ name: 'Attending', price: 0, sold: 42, qty: 60 }],
    needs: 'Needs 2 canteen · 2 rostered',
    attendees: [
      { name: 'Sarah Whitcombe', type: 'Attending', paid: 'RSVP YES', note: '+2 guests' },
      { name: 'Aisha Nasser', type: 'Attending', paid: 'RSVP YES', note: '+1 guest' },
      { name: 'Cal Doyle', type: 'Attending', paid: 'RSVP YES', note: 'Presenting' },
      { name: 'Grant Whitcombe', type: 'Attending', paid: 'RSVP YES', note: '' },
      { name: 'Rob Kinsella', type: '—', paid: 'RSVP NO', note: 'Away that weekend' },
      { name: '12 families yet to reply', type: '', paid: '', note: '' },
    ] },
  { id: 'e3', title: 'Christmas carnival', when: 'Sat 12 Dec 2026 · 11:00am–8:00pm', venue: 'Main Ground + Clubrooms', status: 'on sale', kind: 'Ticketed', cap: 150, budget: 1900, task: 'carn',
    tickets: [
      { name: 'Adult', price: 15, sold: 38, qty: 60 },
      { name: 'Child', price: 8, sold: 31, qty: 60 },
      { name: 'Family (2+3)', price: 40, sold: 17, qty: 30 },
    ],
    needs: 'Needs 4 bar + 2 kitchen + 2 ground · 3 rostered',
    attendees: [
      { name: 'Andrew Pearce', type: 'Family (2+3)', paid: 'PAID', note: '$40 · card' },
      { name: 'Megan Doyle', type: 'Family (2+3)', paid: 'PAID', note: '$40 · card' },
      { name: 'Helen Vaughan', type: 'Adult ×2', paid: 'PAID', note: '$30 · cash' },
      { name: 'Nick Bramley', type: 'Adult', paid: 'UNPAID', note: 'Reserved, invoice sent' },
      { name: 'Priya Raman', type: 'Adult + Child', paid: 'PAID', note: '$23 · card' },
      { name: '+ 63 more ticket holders', type: '', paid: '', note: '' },
    ] },
  { id: 'e4', title: 'Quiz night fundraiser', when: 'Sat 13 Feb 2027 · 7:00–10:30pm', venue: 'Clubrooms', status: 'draft', kind: 'Ticketed', cap: 120, budget: 700, task: null,
    tickets: [{ name: 'Table of 8', price: 160, sold: 0, qty: 15 }, { name: 'Individual', price: 25, sold: 0, qty: 40 }],
    needs: 'Needs 3 bar + 2 kitchen · nobody rostered', attendees: [] },
  { id: 'e5', title: 'Presentation night', when: 'Sat 27 Mar 2027 · 6:30–11:30pm', venue: 'Function Room', status: 'draft', kind: 'Ticketed', cap: 60, budget: 4200, task: 'pres',
    tickets: [{ name: 'Adult', price: 65, sold: 0, qty: 50 }, { name: 'Junior', price: 35, sold: 0, qty: 20 }],
    needs: 'Needs 3 bar + 2 kitchen · nobody rostered', attendees: [] },
]

export const EV_STATUS = {
  'open':    { label: 'OPEN', fg: '#16c784' },
  'on sale': { label: 'ON SALE', fg: '#6366F1' },
  'draft':   { label: 'DRAFT', fg: '#8a90a2' },
}
