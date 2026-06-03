/* BetterIQ — data for the six remaining screens. Our club: Applecross. */

/* ── Our squad (1st Grade core) ──────────────────────────────────────────── */
const IQ_SQUAD = [
  { id: 'p1', name: 'J. Hartley', roles: ['BAT'], order: 1, runs: 642, bat_avg: 53.5, sr: 88, fifties: 6, hundreds: 1, wkts: 4, bowl_avg: 38.2, econ: 5.1, avail: 'available', form5: [88, 12, 104, 41, 67], formAvg: 62.4, vsOpp: 'avg 52.3', last: '2025-03' },
  { id: 'p4', name: 'A. Reddy', roles: ['BAT'], order: 2, runs: 511, bat_avg: 42.6, sr: 79, fifties: 4, hundreds: 0, wkts: 0, avail: 'available', form5: [41, 7, 58, 22, 71], formAvg: 39.8, vsOpp: 'avg 35.8', last: '2025-03' },
  { id: 'p7', name: 'R. Castellano', roles: ['BAT'], order: 3, runs: 367, bat_avg: 30.6, sr: 74, fifties: 2, hundreds: 0, wkts: 6, bowl_avg: 31.0, econ: 4.8, avail: 'available', form5: [33, 61, 19, 4, 27], formAvg: 28.8, vsOpp: 'avg 30.1', last: '2025-03' },
  { id: 'p6', name: 'T. Nguyen', roles: ['WKT', 'BAT'], order: 4, runs: 402, bat_avg: 36.5, sr: 91, fifties: 3, hundreds: 0, wkts: 0, dismissals: 18, avail: 'available', form5: [54, 22, 38, 71, 11], formAvg: 39.2, vsOpp: 'avg 28.0', last: '2025-03' },
  { id: 'p2', name: 'D. Okafor', roles: ['ALL'], order: 5, runs: 388, bat_avg: 29.8, sr: 96, fifties: 2, hundreds: 0, wkts: 24, bowl_avg: 21.7, econ: 4.9, avail: 'available', form5: [44, 18, 33, 9, 52], formAvg: 31.2, vsOpp: '388r · 11w', last: '2025-03' },
  { id: 'p9', name: 'C. Mbatha', roles: ['ALL'], order: 6, runs: 244, bat_avg: 24.4, sr: 102, fifties: 1, hundreds: 0, wkts: 17, bowl_avg: 24.8, econ: 5.2, avail: 'maybe', form5: [12, 41, 8, 28, 19], formAvg: 21.6, vsOpp: 'avg 19.0', last: '2025-02' },
  { id: 'p3', name: 'S. Whitlock', roles: ['BWL'], order: 9, runs: 96, bat_avg: 12.0, sr: 64, wkts: 31, bowl_avg: 16.2, econ: 3.9, best: '5/24', avail: 'available', form5: [3, 2, 4, 1, 5], formAvg: 3.0, vsOpp: '19w @ 14.6', last: '2025-03' },
  { id: 'p5', name: 'M. Petrakis', roles: ['BWL'], order: 10, runs: 142, bat_avg: 11.8, sr: 58, wkts: 27, bowl_avg: 18.9, econ: 4.4, best: '4/31', avail: 'available', form5: [2, 3, 1, 4, 2], formAvg: 2.4, vsOpp: '14w @ 19.2', last: '2025-03' },
  { id: 'p8', name: 'B. Achterberg', roles: ['BWL'], order: 11, runs: 58, bat_avg: 8.3, sr: 52, wkts: 21, bowl_avg: 22.1, econ: 4.6, best: '3/19', avail: 'available', form5: [1, 2, 0, 3, 2], formAvg: 1.6, vsOpp: '8w @ 21.0', last: '2025-03' },
  { id: 'p10', name: 'L. Fenwick', roles: ['BAT'], order: 7, runs: 298, bat_avg: 27.1, sr: 83, fifties: 1, hundreds: 0, wkts: 0, avail: 'available', form5: [22, 48, 14, 31, 9], formAvg: 24.8, vsOpp: 'avg 21.4', last: '2025-03' },
  { id: 'p11', name: 'K. Donato', roles: ['BWL'], order: 8, runs: 78, bat_avg: 13.0, sr: 61, wkts: 14, bowl_avg: 26.4, econ: 5.0, best: '3/28', avail: 'unavailable', form5: [1, 0, 2, 1, 0], formAvg: 0.8, vsOpp: '4w @ 30.0', last: '2025-02' },
  { id: 'p12', name: 'W. Pryce', roles: ['BAT'], order: 3, runs: 188, bat_avg: 23.5, sr: 71, fifties: 1, hundreds: 0, wkts: 0, avail: 'available', form5: [62, 38, 19, 7, 44], formAvg: 34.0, vsOpp: 'avg 26.0', last: '2025-03', grade: '2nd' },
  { id: 'p13', name: 'O. Tahir', roles: ['ALL'], order: 6, runs: 156, bat_avg: 19.5, sr: 94, wkts: 19, bowl_avg: 20.1, econ: 4.5, best: '4/22', avail: 'available', form5: [3, 28, 4, 41, 2], formAvg: 15.6, vsOpp: 'avg 18.0', last: '2025-03', grade: '2nd' },
  { id: 'p14', name: 'N. Calloway', roles: ['WKT', 'BAT'], order: 5, runs: 134, bat_avg: 22.3, sr: 86, avail: 'maybe', form5: [18, 41, 6, 33, 12], formAvg: 22.0, vsOpp: '—', last: '2025-02', grade: '2nd' },
];

const AVAIL_META = {
  available: { label: 'Available', color: 'var(--pb-brand)' },
  maybe: { label: 'Maybe', color: 'var(--pb-amber)' },
  unavailable: { label: 'Out', color: 'var(--pb-red)' },
};

/* ── Match preview (instant, fast) ───────────────────────────────────────── */
const IQ_PREVIEW = {
  opponent: 'Melville', when: 'Sat 7 Jun', home_away: 'Home', venue: 'Tompkins Park', grade: '1st Grade',
  lean: [
    'We hold a 21–14 edge and have won 3 of the last 4 — confidence is with us.',
    'They live and die with Cooper Voss (584 runs) — Whitlock owns him (5 dismissals). Get spin on early.',
    'Their middle order folds after the 3rd wicket falls (stands rarely pass 20). Two quick ones and the game tilts.',
    'Bat first if we win the toss — they\u2019ve only chased 230+ twice all season.',
  ],
  ladder: [
    { pos: 3, team: 'Applecross', played: 13, won: 8, lost: 5, pts: 34, us: true },
    { pos: 5, team: 'Melville', played: 14, won: 7, lost: 6, pts: 30 },
  ],
  ladder_context: 'A win lifts us above Willetton into 2nd; Melville stay mid-table.',
  par: { score: 228, note: 'Median winning first-innings score at Tompkins Park this season.' },
};

/* ── Selection analysis (a saved BetterSelect XI for the Melville fixture) ── */
const IQ_SELECTION = {
  fixture: 'vs Melville · Sat 7 Jun · Home',
  verdict: 'A well-balanced XI — strong on paper, but one spinner light for a ground where spin has done the damage.',
  balance: [
    { label: 'Specialist bats', value: 5, ok: true },
    { label: 'All-rounders', value: 2, ok: true },
    { label: 'Specialist bowlers', value: 3, ok: true },
    { label: 'Pace / spin', value: '3 / 1', warn: true },
    { label: 'Keeper', value: 1, ok: true },
    { label: 'Openers', value: 2, ok: true },
    { label: 'Left / right', value: '3 / 8', ok: true },
  ],
  warnings: [
    { tone: 'amber', text: 'Only one frontline spinner (Whitlock) — spin has taken 41% of wickets at Tompkins Park. Consider Tahir for Donato.' },
    { tone: 'faint', text: 'Batting depth thins after No.7 — a top-order collapse would expose the tail early.' },
  ],
  xi: [
    { id: 'p1', name: 'J. Hartley', role: 'BAT', no: 1, formAvg: 62.4, vsOpp: 52.3, avail: 'available' },
    { id: 'p4', name: 'A. Reddy', role: 'BAT', no: 2, formAvg: 39.8, vsOpp: 35.8, avail: 'available' },
    { id: 'p7', name: 'R. Castellano', role: 'BAT', no: 3, formAvg: 28.8, vsOpp: 30.1, avail: 'available' },
    { id: 'p6', name: 'T. Nguyen', role: 'WK', no: 4, formAvg: 39.2, vsOpp: 28.0, avail: 'available' },
    { id: 'p2', name: 'D. Okafor', role: 'ALL', no: 5, formAvg: 31.2, vsOpp: 33.0, avail: 'available' },
    { id: 'p9', name: 'C. Mbatha', role: 'ALL', no: 6, formAvg: 21.6, vsOpp: 19.0, avail: 'maybe', flag: 'maybe' },
    { id: 'p10', name: 'L. Fenwick', role: 'BAT', no: 7, formAvg: 24.8, vsOpp: 21.4, avail: 'available' },
    { id: 'p11', name: 'K. Donato', role: 'BWL', no: 8, formAvg: 0.8, vsOpp: 30.0, avail: 'unavailable', flag: 'out' },
    { id: 'p3', name: 'S. Whitlock', role: 'BWL', no: 9, formAvg: 3.0, vsOpp: 14.6, avail: 'available' },
    { id: 'p5', name: 'M. Petrakis', role: 'BWL', no: 10, formAvg: 2.4, vsOpp: 19.2, avail: 'available' },
    { id: 'p8', name: 'B. Achterberg', role: 'BWL', no: 11, formAvg: 1.6, vsOpp: 21.0, avail: 'available' },
  ],
  promote: [
    { id: 'p13', name: 'O. Tahir', why: 'In form (4/22 last start), eligible, and the second spinner this ground rewards.' },
    { id: 'p12', name: 'W. Pryce', why: 'Averaging 34 in his last 5 in 2nd grade — pushing hard for a top-order spot.' },
  ],
  watch: [
    { id: 'p11', name: 'K. Donato', why: 'Named but unavailable — needs replacing.' },
    { id: 'p9', name: 'C. Mbatha', why: 'Only a maybe, and out of touch (21.6 avg in last 5).' },
  ],
  best_xi_note: 'Suggested best-available XI swaps Donato → Tahir and keeps the rest. Matches the BetterSelect eligibility pool exactly.',
};

/* ── Player trends ───────────────────────────────────────────────────────── */
const IQ_TRENDS = {
  movers: {
    bat_rising: [
      { id: 'p6', name: 'T. Nguyen', delta: 11.4, now: 36.5, was: 25.1 },
      { id: 'p10', name: 'L. Fenwick', delta: 6.8, now: 27.1, was: 20.3 },
    ],
    bat_falling: [
      { id: 'p7', name: 'R. Castellano', delta: -7.2, now: 30.6, was: 37.8 },
    ],
    bowl_rising: [
      { id: 'p3', name: 'S. Whitlock', delta: -4.1, now: 16.2, was: 20.3, metric: 'avg' },
      { id: 'p13', name: 'O. Tahir', delta: -3.5, now: 20.1, was: 23.6, metric: 'avg' },
    ],
    bowl_falling: [
      { id: 'p11', name: 'K. Donato', delta: 5.2, now: 26.4, was: 21.2, metric: 'avg' },
    ],
  },
  emerging: [
    { id: 'p12', name: 'W. Pryce', age: 19, note: '34 avg in 2nd grade — knocking on the door.' },
    { id: 'p15', name: 'H. Sandhu', age: 17, note: 'Colts star, 3 fifties — one to watch next season.' },
  ],
  // deep dive on the club's #1
  player: {
    id: 'p1', name: 'Jordan Hartley', role: 'Top-order batter', verdict: ['Peak form', 'Most valuable bat'],
    career: { matches: 142, runs: 5840, avg: 44.6, hundreds: 9, fifties: 31, hs: 167 },
    season: { runs: 642, avg: 53.5, sr: 88, fifties: 6, hundreds: 1 },
    form5: [88, 12, 104, 41, 67],
    shape: { peak: '2024/25', consistency: 'High (σ 28)', trend: 'Rising' },
    milestones: [{ label: '6,000 career runs', need: 160, eta: '4–5 innings' }, { label: '10th century', need: 1, eta: 'this season' }],
    seasons: [
      { yr: '20/21', runs: 388, avg: 29.8 }, { yr: '21/22', runs: 472, avg: 37.2 },
      { yr: '22/23', runs: 514, avg: 39.5 }, { yr: '23/24', runs: 596, avg: 46.0 },
      { yr: '24/25', runs: 642, avg: 53.5 },
    ],
    deep: {
      conversion: { fifties_to_100: '14%', starts_wasted: '31% (20–40 then out)' },
      reliability: { floor: 14, median: 48, ceiling: 104 },
      situation: [{ k: 'Batting first', v: 'avg 58.1' }, { k: 'Chasing', v: 'avg 47.2' }, { k: 'vs spin', v: 'SR 78' }, { k: 'vs pace', v: 'SR 94' }],
      win_value: { with: '71% win', without: '44% win' },
      similar: ['A. Reddy', 'C. Falzon (Melville)'],
      by_position: [{ k: 'Open', v: 'avg 56' }, { k: 'No.3', v: 'avg 41' }],
      get_out: [{ type: 'caught', pct: 52 }, { type: 'bowled', pct: 21 }, { type: 'lbw', pct: 18 }, { type: 'run out', pct: 9 }],
    },
  },
};

/* ── Team analysis ───────────────────────────────────────────────────────── */
const IQ_TEAM = {
  season: '2024/25', grade: '1st Grade',
  season_winpct: { '2020/21': 45, '2021/22': 50, '2022/23': 55, '2023/24': 58, '2024/25': 62 },
  season_record: { '2020/21': '6–7', '2021/22': '7–6', '2022/23': '8–5', '2023/24': '8–4', '2024/25': '8–5' },
  overview: {
    record: { played: 13, won: 8, lost: 5, win_pct: 62 },
    win: ['Top three fire — we average 251 when an opener passes 50.', 'Spin chokes the middle — Whitlock & co. average 17.', 'We defend well: 6 of 8 wins came batting first.'],
    lose: ['Top order collapses — 4 of 5 losses we were 3 down inside 15 overs.', 'Death bowling leaks — opposition score 8.1/over in the last 5.', 'We struggle chasing 240+ (1 from 4).'],
    bat_first: { played: 7, won: 6 }, chase: { played: 6, won: 2 },
    par: 228, par_note: 'Median winning first-innings score across our grounds.',
    bands: [{ band: '< 180', win: 18 }, { band: '180–219', win: 47 }, { band: '220–249', win: 78 }, { band: '250+', win: 92 }],
    venues: [{ venue: 'Tompkins Park (H)', w: 6, l: 1, p: 7 }, { venue: 'Away grounds', w: 2, l: 4, p: 6 }],
  },
  batting: {
    profile: { avg_score: 232, run_rate: 4.7, top4_share: 64 },
    starts: { reached20: '58%', converted50: '34%' },
    partnerships: [{ w: 1, avg: 38 }, { w: 2, avg: 52 }, { w: 3, avg: 47 }, { w: 4, avg: 33 }, { w: 5, avg: 24 }],
    best_pairs: [{ pair: 'Hartley & Reddy', avg: 61, runs: 488 }, { pair: 'Nguyen & Okafor', avg: 44, runs: 308 }],
    collapse: 'Lost 3+ for under 25 runs in 5 of 13 innings — a recurring wobble through the middle.',
  },
  bowling: {
    summary: { avg: 21.4, econ: 4.5, sr: 28 },
    attack: [{ name: 'Whitlock', role: 'Spin · strike', share: 24 }, { name: 'Petrakis', role: 'Pace · new ball', share: 21 }, { name: 'Okafor', role: 'Pace · all-round', share: 18 }, { name: 'Achterberg', role: 'Pace · first change', share: 16 }],
    discipline: { extras_per_inns: 11.2, wides: 6.4, no_balls: 1.1 },
    wickets: { top_order: '46%', bowled_lbw: '38%' },
  },
  players: {
    captaincy: [{ name: 'J. Hartley', as_capt: '9–4', note: 'Strong under his lead' }],
    all_rounders: [{ name: 'D. Okafor', rating: 84 }, { name: 'O. Tahir', rating: 66 }, { name: 'C. Mbatha', rating: 58 }],
    fielders: [{ name: 'T. Nguyen', label: '18 dismissals (kpr)' }, { name: 'A. Reddy', label: '11 catches' }, { name: 'L. Fenwick', label: '9 catches' }],
  },
};

/* ── Match review ────────────────────────────────────────────────────────── */
const IQ_REVIEW_GAMES = [
  { id: 'g1', opp: 'Melville', grade: '1st', date: '8 Mar 2025', result: 'W', line: 'Won by 34 runs', us: true },
  { id: 'g2', opp: 'Fremantle', grade: '1st', date: '1 Mar 2025', result: 'W', line: 'Won by 6 wkts' },
  { id: 'g3', opp: 'Willetton', grade: '1st', date: '22 Feb 2025', result: 'L', line: 'Lost by 18 runs' },
  { id: 'g4', opp: 'Bayswater-Morley', grade: '1st', date: '15 Feb 2025', result: 'W', line: 'Won by 52 runs' },
  { id: 'g5', opp: 'Palmyra', grade: '1st', date: '8 Feb 2025', result: 'L', line: 'Lost by 3 wkts' },
];
const IQ_GAME_REVIEW = {
  id: 'g1', opp: 'Melville', date: '8 Mar 2025', venue: 'Tompkins Park', grade: '1st Grade',
  result: 'WIN', margin: 'Won by 34 runs', us_score: '7/241', them_score: '207 all out',
  turning_point: 'Hartley\u2019s 88 set a defendable 241, then Whitlock\u2019s 4/38 ripped the middle order out — Melville lost 4/19 in the 30s and never recovered.',
  top_bat: [{ name: 'J. Hartley', score: '88 (96)' }, { name: 'T. Nguyen', score: '54 (47)' }, { name: 'D. Okafor', score: '33 (28)' }],
  top_bowl: [{ name: 'S. Whitlock', fig: '4/38' }, { name: 'M. Petrakis', fig: '3/41' }, { name: 'D. Okafor', fig: '2/35' }],
  best_partnership: 'Hartley & Nguyen — 96 for the 4th',
  extras: '14 (6 wides)', collapse: 'Melville 4/19 between overs 28–34',
};

/* ── Opposition player (Melville) profile + scouting tags ────────────────── */
const IQ_OPP_PLAYER = {
  club: 'Melville', name: 'Cooper Voss',
  season: { runs: 584, avg: 48.7, sr: 96, hs: 142, fifties: 4, hundreds: 1, inns: 14 },
  bowling: null,
  form5: [88, 12, 142, 34, 67],
  get_out: [{ type: 'caught', pct: 44 }, { type: 'bowled', pct: 22 }, { type: 'stumped', pct: 18 }, { type: 'lbw', pct: 16 }],
  vs_us: { runs: 214, avg: 30.6, dismissed_by: 'Whitlock 5×, Petrakis 3×, Achterberg 2×' },
  tags: { hand: 'Right', bowl_arm: '—', bowl_type: 'Occasional off-spin', role: 'Top-order bat', keeper: false, danger: true, notes: 'Explosive square of the wicket. Patient early, then accelerates hard once set — but vulnerable to quality spin into the breeze. Has fallen to Whitlock 5 times: gets him driving against the turn.' },
};

/* ── Club form / momentum (Overview hub) ─────────────────────────────────── */
const IQ_CLUB_FORM = {
  last10: ['W', 'W', 'L', 'W', 'L', 'W', 'W', 'L', 'W', 'W'],
  win_pct: 62,
  // cumulative points trajectory across the season (round → points)
  points_curve: [4, 4, 8, 8, 12, 16, 16, 20, 22, 26, 26, 30, 34],
  ladder_pos: 3, ladder_total: 10, ladder_move: 2, // climbed 2 places recently
  streak: 'Won 2',
  run_diff: '+312', // net runs across season
  season: '2024/25',
  this_week: [
    { step: 'Preview', label: 'Scout Melville', state: 'ready', route: 'preview' },
    { step: 'Select', label: 'Confirm XI', state: 'attention', route: 'selection' },
    { step: 'Match day', label: 'Sat 7 Jun', state: 'upcoming', route: null },
    { step: 'Review', label: 'Auto post-match', state: 'locked', route: 'review' },
  ],
};

/* ── Signature viz: radar profiles + scoring zones + phases ───────────────── */
/* Radar values are 0–100, normalised against grade average (the 50 ring). */
const IQ_VIZ = {
  // batter radar axes
  bat_axes: [
    { key: 'volume', label: 'Volume' },
    { key: 'average', label: 'Average' },
    { key: 'strike', label: 'Strike rate' },
    { key: 'consistency', label: 'Consistency' },
    { key: 'conversion', label: 'Conversion' },
    { key: 'impact', label: 'Match impact' },
  ],
  bowl_axes: [
    { key: 'wickets', label: 'Wickets' },
    { key: 'average', label: 'Average' },
    { key: 'economy', label: 'Economy' },
    { key: 'strike', label: 'Strike rate' },
    { key: 'hauls', label: 'Big hauls' },
    { key: 'top_order', label: 'Top-order' },
  ],
  radar: {
    // our players
    p1: { kind: 'bat', values: [92, 88, 70, 82, 58, 90] }, // Hartley
    p4: { kind: 'bat', values: [78, 74, 64, 70, 52, 66] }, // Reddy
    p6: { kind: 'bat', values: [74, 70, 80, 66, 50, 62] }, // Nguyen (keeper-bat)
    p7: { kind: 'bat', values: [62, 56, 60, 54, 44, 50] }, // Castellano
    p3: { kind: 'bowl', values: [90, 88, 84, 80, 75, 70] }, // Whitlock
    p2: { kind: 'bowl', values: [72, 64, 60, 66, 48, 58] }, // Okafor (bowl)
    // opposition
    m1: { kind: 'bat', values: [88, 80, 86, 55, 62, 85] }, // Voss
    m6: { kind: 'bowl', values: [86, 82, 70, 84, 78, 80] }, // Mockridge
  },
  // scoring zones — % of runs by area, batter's view, 8 sectors clockwise from straight.
  zones: {
    m1: { hand: 'RH', sectors: [10, 22, 20, 6, 5, 14, 18, 5], note: 'Dominant square of the wicket — punishes width through point and cover, and works the gaps to mid-wicket. Quiet straight and behind square on the leg side.' },
    p1: { hand: 'RH', sectors: [18, 16, 19, 8, 6, 10, 17, 6], note: 'Classical V — strong straight and through cover, rotates well into the leg side. Few risky areas.' },
  },
  // innings phase estimate (scorecard-derived, labelled as estimate)
  phases_opp: { // Melville typical innings shape
    name: 'Melville', total: 218,
    phases: [
      { label: 'Powerplay', overs: '1–10', runs: 58, wkts: 2, rr: 5.8 },
      { label: 'Middle', overs: '11–35', runs: 118, wkts: 5, rr: 4.7 },
      { label: 'Death', overs: '36–45', runs: 42, wkts: 3, rr: 4.2 },
    ],
    insight: 'They load up early then stall — the middle overs are where we squeeze, and the death rarely accelerates.',
  },
};

Object.assign(window, {
  IQ_SQUAD, AVAIL_META, IQ_PREVIEW, IQ_SELECTION, IQ_TRENDS, IQ_TEAM, IQ_REVIEW_GAMES, IQ_GAME_REVIEW, IQ_OPP_PLAYER,
  IQ_CLUB_FORM, IQ_VIZ,
});
