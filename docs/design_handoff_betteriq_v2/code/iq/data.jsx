/* BetterIQ — realistic mock data (WA community/grade cricket).
   Our club: Applecross CC. Flagship opponent: Melville CC. */

const IQ_CLUB = { name: 'Applecross', short: 'APP' };

const IQ_UPCOMING = [
  { fixture_id: 'fx1', opp_key: 'melville', opponent_name: 'Melville', played_on: 'Sat 7 Jun', home_away: 'Home', venue: 'Tompkins Park', team: '1st Grade', coverage: 'rich' },
  { fixture_id: 'fx2', opp_key: 'willetton', opponent_name: 'Willetton', played_on: 'Sat 14 Jun', home_away: 'Away', venue: 'Burrendah Reserve', team: '1st Grade', coverage: 'rich' },
  { fixture_id: 'fx3', opp_key: 'bicton', opponent_name: 'Bicton-Attadale', played_on: 'Sat 21 Jun', home_away: 'Home', venue: 'Bicton Reserve', team: '2nd Grade', coverage: 'rich' },
  { fixture_id: 'fx4', opp_key: 'rossmoyne', opponent_name: 'Rossmoyne', played_on: 'Sat 28 Jun', home_away: 'Away', venue: 'Shelley Reserve', team: '1st Grade', coverage: 'partial' },
];

const IQ_OPPONENTS = [
  { opp_key: 'melville', name: 'Melville', meetings: 38, last_played: '2025-03-08', coverage: 'rich' },
  { opp_key: 'willetton', name: 'Willetton', meetings: 31, last_played: '2025-02-22', coverage: 'rich' },
  { opp_key: 'fremantle', name: 'Fremantle', meetings: 44, last_played: '2024-12-14', coverage: 'rich' },
  { opp_key: 'bayswater', name: 'Bayswater-Morley', meetings: 27, last_played: '2024-11-30', coverage: 'rich' },
  { opp_key: 'bicton', name: 'Bicton-Attadale', meetings: 22, last_played: '2025-01-18', coverage: 'rich' },
  { opp_key: 'rossmoyne', name: 'Rossmoyne', meetings: 19, last_played: '2024-12-07', coverage: 'partial' },
  { opp_key: 'mtpleasant', name: 'Mount Pleasant', meetings: 16, last_played: '2024-10-26', coverage: 'rich' },
  { opp_key: 'canningvale', name: 'Canning Vale', meetings: 12, last_played: '2024-11-09', coverage: 'partial' },
  { opp_key: 'palmyra', name: 'Palmyra', meetings: 24, last_played: '2024-12-21', coverage: 'rich' },
  { opp_key: 'kelmscott', name: 'Kelmscott', meetings: 9, last_played: '2024-10-12', coverage: 'partial' },
];

/* Club MVP impact board (0–100 season value) */
const IQ_MVP = [
  { player_id: 'p1', name: 'J. Hartley', role: 'Top-order bat', score: 91, runs: 642, wkts: 4, fifties: 6, sub: '642 runs · 4 wkts · 6×50' },
  { player_id: 'p2', name: 'D. Okafor', role: 'All-rounder', score: 84, runs: 388, wkts: 24, fifties: 2, sub: '388 runs · 24 wkts · 2×50' },
  { player_id: 'p3', name: 'S. Whitlock', role: 'Spin bowler', score: 79, runs: 96, wkts: 31, fifties: 0, sub: '31 wkts @ 16.2 · econ 3.9' },
  { player_id: 'p4', name: 'A. Reddy', role: 'Opening bat', score: 74, runs: 511, wkts: 0, fifties: 4, sub: '511 runs @ 42.6 · 4×50' },
  { player_id: 'p5', name: 'M. Petrakis', role: 'Pace bowler', score: 71, runs: 142, wkts: 27, fifties: 0, sub: '27 wkts @ 18.9 · econ 4.4' },
  { player_id: 'p6', name: 'T. Nguyen', role: 'Keeper-bat', score: 66, runs: 402, wkts: 0, fifties: 3, sub: '402 runs · 18 dismissals' },
  { player_id: 'p7', name: 'R. Castellano', role: 'Middle-order', score: 58, runs: 367, wkts: 6, fifties: 2, sub: '367 runs · 6 wkts' },
  { player_id: 'p8', name: 'B. Achterberg', role: 'Pace bowler', score: 52, runs: 58, wkts: 21, fifties: 0, sub: '21 wkts @ 22.1' },
];

/* ── Instant report (held data) — Melville ──────────────────────────────────── */
const IQ_REPORT = {
  opponent: { name: 'Melville', opp_key: 'melville' },
  head_to_head: {
    meetings: 38, wins: 21, losses: 14, draws: 2, ties: 1, win_pct: 55,
    home: { wins: 13, played: 20 }, away: { wins: 8, played: 18 },
    recent_form: ['W', 'L', 'W', 'W', 'L'],
    recent: [
      { played_at: '8 Mar 2025', grade_name: '1st Grade', our_venue: 'H', result: 'WIN', winning_team: 'Applecross by 34' },
      { played_at: '16 Nov 2024', grade_name: '1st Grade', our_venue: 'A', result: 'LOSS', winning_team: 'Melville by 5 wkts' },
      { played_at: '2 Mar 2024', grade_name: '1st Grade', our_venue: 'H', result: 'WIN', winning_team: 'Applecross by 61' },
      { played_at: '25 Nov 2023', grade_name: '1st Grade', our_venue: 'A', result: 'WIN', winning_team: 'Applecross by 3 wkts' },
      { played_at: '4 Mar 2023', grade_name: '1st Grade', our_venue: 'H', result: 'LOSS', winning_team: 'Melville by 22' },
    ],
  },
  our_performers: {
    batting: [
      { player_id: 'p1', name: 'J. Hartley', runs: 418, average: 52.3, active: true },
      { player_id: 'p4', name: 'A. Reddy', runs: 286, average: 35.8, active: true },
      { player_id: 'p7', name: 'R. Castellano', runs: 241, average: 30.1, active: true },
      { player_id: 'px', name: 'G. Mallory', runs: 198, average: 28.3, active: false },
    ],
    bowling: [
      { player_id: 'p3', name: 'S. Whitlock', wickets: 19, average: 14.6, active: true },
      { player_id: 'p5', name: 'M. Petrakis', wickets: 14, average: 19.2, active: true },
      { player_id: 'p2', name: 'D. Okafor', wickets: 11, average: 21.7, active: true },
    ],
  },
  last_meeting: {
    result: 'WIN', played_at: '8 Mar 2025', venue: 'Tompkins Park',
    our_runs: '7/241', opp_runs: '207 all out',
    our_top_bat: { name: 'J. Hartley', runs: 88 },
    our_top_bowl: { name: 'S. Whitlock', wickets: 4, runs: 38 },
  },
  venues: [
    { venue: 'Tompkins Park (H)', wins: 13, losses: 6, played: 20 },
    { venue: 'Len Shearer Reserve (A)', wins: 5, losses: 7, played: 13 },
    { venue: 'Bull Creek Reserve', wins: 3, losses: 1, played: 5 },
  ],
  matchups: {
    bowler_dominance: [
      { bowler: 'Whitlock', batter: 'Voss', dismissals: 5, how: ['lbw', 'bowled', 'stumped'], runs_made: 61, active: true },
      { bowler: 'Whitlock', batter: 'Dimasi', dismissals: 3, how: ['caught', 'stumped'], runs_made: 44, active: true },
      { bowler: 'Whitlock', batter: 'Larkin', dismissals: 2, how: ['lbw'], runs_made: 18, active: true },
      { bowler: 'Petrakis', batter: 'Voss', dismissals: 3, how: ['caught', 'bowled'], runs_made: 52, active: true },
      { bowler: 'Petrakis', batter: 'Saunders', dismissals: 4, how: ['caught'], runs_made: 39, active: true },
      { bowler: 'Petrakis', batter: 'Dimasi', dismissals: 2, how: ['lbw'], runs_made: 27, active: true },
      { bowler: 'Okafor', batter: 'Saunders', dismissals: 3, how: ['caught', 'bowled'], runs_made: 31, active: true },
      { bowler: 'Okafor', batter: 'Trento', dismissals: 2, how: ['caught'], runs_made: 22, active: true },
      { bowler: 'Achterberg', batter: 'Larkin', dismissals: 3, how: ['bowled', 'lbw'], runs_made: 24, active: true },
      { bowler: 'Achterberg', batter: 'Voss', dismissals: 2, how: ['caught'], runs_made: 33, active: true },
    ],
  },
};

/* ── Live dossier — Melville ─────────────────────────────────────────────────── */
const IQ_DOSSIER = {
  status: 'ready',
  built_at: '2025-06-02T09:14:00',
  opponent: { name: 'Melville' },
  selected_team_name: '1st Grade',
  teams: [
    { grade_id: 'g1', team_name: '1st Grade', matches: 14 },
    { grade_id: 'g2', team_name: '2nd Grade', matches: 13 },
    { grade_id: 'g3', team_name: '3rd Grade', matches: 12 },
  ],
  game_plan: {
    one_liner: 'Strangle the top three early — their middle order can\u2019t rebuild against spin.',
    remove_early: { name: 'Cooper Voss', why: 'scores 61% of his runs in the first 20 overs' },
    see_off: { name: 'Lucas Dimasi', why: 'patient anchor — deny strike, attack the other end' },
    target_bowler: { name: 'Reece Mockridge', economy: 6.8 },
    key_warning: 'If Voss is in past the 15th over he goes big — they\u2019ve chased 240+ twice when he stays.',
  },
  danger_batters: [
    { player_id: 'm1', name: 'Cooper Voss', runs: 584, average: 48.7, strike_rate: 96, high_score: 142, fifties: 4, hundreds: 1, form: 'hot', recent_scores: ['88', '12', '142', '34', '67*'], vs_us: { runs: 214, average: 30.6 }, risk: 'high', confidence: 'high', plan: 'Spin from over one; pack the off-side ring.', key_note: 'Their match-winner — explosive square of the wicket, but Whitlock owns him (5 dismissals).', alert: { level: 'danger', danger: ['Hot form', 'Match-winner'] } },
    { player_id: 'm2', name: 'Lucas Dimasi', runs: 441, average: 40.1, strike_rate: 71, high_score: 96, fifties: 5, hundreds: 0, form: 'warm', recent_scores: ['44', '51', '23', '8', '62'], vs_us: { runs: 138, average: 27.6 }, risk: 'medium', confidence: 'high', plan: 'Patient anchor — deny the single, build pressure.', key_note: 'The glue. Rarely the danger himself but lets others tee off — break the stand early.', alert: null },
    { player_id: 'm3', name: 'Harry Saunders', runs: 312, average: 28.4, strike_rate: 88, high_score: 74, fifties: 2, hundreds: 0, form: 'cold', recent_scores: ['12', '4', '31', '0', '18'], vs_us: { runs: 71, average: 14.2 }, risk: 'low', confidence: 'medium', plan: 'Out of touch — attack the stumps, he\u2019ll drag on.', key_note: 'In a rut and we have his number (Petrakis 4×). Could be a free wicket.', alert: { level: 'caution', caution: ['Out of form', 'We dominate him'] } },
    { player_id: 'm4', name: 'Jai Larkin', runs: 268, average: 24.4, strike_rate: 104, high_score: 58, fifties: 1, hundreds: 0, form: 'warm', recent_scores: ['41', '7', '58', '22', '13'], vs_us: { runs: 49, average: 12.3 }, risk: 'medium', confidence: 'medium', plan: 'Counter-attacker — give him nothing wide early.', key_note: 'High-risk hitter. Boom or bust; Achterberg has bounced him out 3 times.', alert: null },
    { player_id: 'm5', name: 'Ben Trento', runs: 224, average: 32.0, strike_rate: 79, high_score: 61, fifties: 2, hundreds: 0, form: 'warm', recent_scores: ['33', '61', '19', '27', '14'], vs_us: { runs: 88, average: 22.0 }, risk: 'medium', confidence: 'medium', plan: 'Finisher — keep him off strike at the death.', key_note: 'Lower-order accelerator. Dangerous in the last 10 if the platform\u2019s there.', alert: null },
  ],
  danger_bowlers: [
    { player_id: 'm6', name: 'Reece Mockridge', wickets: 29, average: 17.2, economy: 4.6, best: '5/24', form: 'hot', recent_wickets: [3, 2, 5, 1, 4], vs_us: { wickets: 12, average: 19.4 }, risk: 'high', confidence: 'high', plan: 'New-ball spearhead — see off his first spell, cash in later.', key_note: 'Their attack leader — swings it both ways with the new ball. Survive him and the runs come.', alert: { level: 'danger', danger: ['Leading wicket-taker', 'Hot form'] } },
    { player_id: 'm7', name: 'Aarav Sharma', wickets: 24, average: 19.8, economy: 3.7, best: '4/19', form: 'warm', recent_wickets: [2, 3, 1, 2, 4], vs_us: { wickets: 8, average: 24.1 }, risk: 'medium', confidence: 'high', plan: 'Miserly off-spinner — rotate strike, don\u2019t let him settle.', key_note: 'Chokes the middle overs at 3.7 an over. Pressure-builder more than a strike bowler.', alert: null },
    { player_id: 'm8', name: 'Dylan Okereke', wickets: 19, average: 24.5, economy: 5.2, best: '3/31', form: 'warm', recent_wickets: [1, 2, 3, 0, 2], vs_us: { wickets: 5, average: 31.0 }, risk: 'medium', confidence: 'medium', plan: 'First-change quick — target him square, he leaks boundaries.', key_note: 'Honest seamer, takes wickets but goes at 5+. A release-valve option for our bats.', alert: null },
    { player_id: 'm9', name: 'Sam Holcombe', wickets: 14, average: 28.1, economy: 4.9, best: '3/28', form: 'cold', recent_wickets: [1, 0, 2, 1, 0], vs_us: { wickets: 3, average: 36.7 }, risk: 'low', confidence: 'low', plan: 'Part-time spin — take him down, he\u2019s their weak link.', key_note: 'Fifth-bowler filler. Wickets dry up against set batters — the over to attack.', alert: { level: 'caution', caution: ['Out of form'] } },
  ],
  how_they_win: [
    'Voss or Dimasi bats deep into the innings (200+ when either passes 50).',
    'Mockridge strikes with the new ball — 71% of their wins feature an early breakthrough.',
    'They defend totals better than they chase — 9 of 11 wins batting first.',
  ],
  how_they_lose: [
    'Top three back in the shed inside 12 overs — middle order can\u2019t rebuild.',
    'Spin through the middle overs: they average 22 fewer runs when spin opens.',
    'Chasing 230+ — only 2 successful chases above that all season.',
  ],
  dismissal_breakdown: [
    { type: 'caught', count: 71, pct: 47 }, { type: 'bowled', count: 34, pct: 22 },
    { type: 'lbw', count: 22, pct: 15 }, { type: 'run out', count: 14, pct: 9 },
    { type: 'stumped', count: 11, pct: 7 },
  ],
  partnerships: [
    { wicket: 1, avg_partnership: 44 }, { wicket: 2, avg_partnership: 51 },
    { wicket: 3, avg_partnership: 38 }, { wicket: 4, avg_partnership: 22 },
    { wicket: 5, avg_partnership: 17 }, { wicket: 6, avg_partnership: 14 },
    { wicket: 7, avg_partnership: 9 },
  ],
  partnership_insight: 'A clear cliff after the 3rd wicket — once three are down, stands rarely pass 20. Break the top order and the innings folds.',
  historical_threats: [
    { player_id: 'h1', name: 'C. Falzon', runs: 312, average: 44.6 },
    { player_id: 'h2', name: 'W. Krieg', runs: 188, average: 37.6 },
    { player_id: 'h3', name: 'N. Beaumont', runs: 156, average: 31.2 },
  ],
  batting: [
    { player_id: 'm1', name: 'Cooper Voss', innings: 14, runs: 584, average: 48.7, strike_rate: 96, high_score: 142, fifties: 4, hundreds: 1, recent_scores: ['88', '12', '142', '34', '67*'], form: 'hot', vs_us: { runs: 214, average: 30.6 } },
    { player_id: 'm2', name: 'Lucas Dimasi', innings: 14, runs: 441, average: 40.1, strike_rate: 71, high_score: 96, fifties: 5, hundreds: 0, recent_scores: ['44', '51', '23', '8', '62'], vs_us: { runs: 138, average: 27.6 } },
    { player_id: 'm5', name: 'Ben Trento', innings: 13, runs: 224, average: 32.0, strike_rate: 79, high_score: 61, fifties: 2, hundreds: 0, recent_scores: ['33', '61', '19', '27', '14'], vs_us: { runs: 88, average: 22.0 } },
    { player_id: 'm3', name: 'Harry Saunders', innings: 14, runs: 312, average: 28.4, strike_rate: 88, high_score: 74, fifties: 2, hundreds: 0, recent_scores: ['12', '4', '31', '0', '18'], vs_us: { runs: 71, average: 14.2 } },
    { player_id: 'm4', name: 'Jai Larkin', innings: 12, runs: 268, average: 24.4, strike_rate: 104, high_score: 58, fifties: 1, hundreds: 0, recent_scores: ['41', '7', '58', '22', '13'], vs_us: { runs: 49, average: 12.3 } },
    { player_id: 'm10', name: 'Oscar Pendrey', innings: 11, runs: 187, average: 20.8, strike_rate: 74, high_score: 45, fifties: 0, hundreds: 0, recent_scores: ['22', '11', '45', '6', '19'], vs_us: null },
    { player_id: 'm11', name: 'Kade Bilic', innings: 9, runs: 122, average: 17.4, strike_rate: 68, high_score: 38, fifties: 0, hundreds: 0, recent_scores: ['5', '38', '14', '2', '21'], vs_us: null },
  ],
  bowling: [
    { player_id: 'm6', name: 'Reece Mockridge', overs: 118, wickets: 29, average: 17.2, economy: 4.6, best: '5/24', recent_wickets: [3, 2, 5, 1, 4] },
    { player_id: 'm7', name: 'Aarav Sharma', overs: 126, wickets: 24, average: 19.8, economy: 3.7, best: '4/19', recent_wickets: [2, 3, 1, 2, 4] },
    { player_id: 'm8', name: 'Dylan Okereke', overs: 89, wickets: 19, average: 24.5, economy: 5.2, best: '3/31', recent_wickets: [1, 2, 3, 0, 2] },
    { player_id: 'm9', name: 'Sam Holcombe', overs: 64, wickets: 14, average: 28.1, economy: 4.9, best: '3/28', recent_wickets: [1, 0, 2, 1, 0] },
    { player_id: 'm12', name: 'Reece Mockridge Jr', overs: 41, wickets: 8, average: 31.4, economy: 5.6, best: '2/22', recent_wickets: [0, 1, 1, 2, 0] },
  ],
  coverage: { notes: ['Built from scorecard data only — no ball-by-ball. Strike rates and economies are innings-level estimates.'] },
};

Object.assign(window, { IQ_CLUB, IQ_UPCOMING, IQ_OPPONENTS, IQ_MVP, IQ_REPORT, IQ_DOSSIER });
