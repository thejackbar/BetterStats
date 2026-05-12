// src/lib/mockData.js
// Fallback data used while real API responses are empty or loading.
// Shape matches the FastAPI backend responses (runs_scored, economy_rate,
// by_grade, by_position, upcoming_milestones, etc.) so the views render
// identically when wired to the real /api/* endpoints.

export const mockClub = {
  name: "Acton Cricket Club",
  short: "ACTON",
  primary_color: "#0a0d14",
  accent_color: "#16c784",
  season_label: "2025/26 SEASON",
};

export const mockClubSummary = {
  match_count: 184,
  player_count: 47,
  win_rate: 0.642,
  total_runs: 24817,
  total_wickets: 921,
  total_centuries: 38,
  total_five_fers: 21,
  active_streak: { type: "WIN", count: 5 },
  results_form: ["W", "W", "L", "W", "W", "D", "W", "W", "L", "W"],
};

export const mockKpiTrends = {
  win_rate:    [0.48, 0.52, 0.51, 0.55, 0.60, 0.58, 0.61, 0.63, 0.66, 0.64],
  runs_per:    [180, 195, 210, 188, 220, 235, 215, 240, 250, 245],
  wickets_per: [6.2, 7.1, 6.5, 7.8, 7.4, 8.1, 7.9, 8.6, 8.3, 8.7],
};

export const mockTopRuns = [
  { id: 1,  name: "Jack Banner",     runs: 1217, avg: 52.9, sr: 88.3, hs: 142,  trend: [12, 24, 45, 38, 67, 41, 88, 102, 76, 142] },
  { id: 2,  name: "Tom Whitfield",   runs:  984, avg: 41.0, sr: 76.5, hs:  118, trend: [22, 35, 18, 52, 41, 64, 38, 51, 72, 118] },
  { id: 3,  name: "Reggie Stone",    runs:  812, avg: 38.6, sr: 81.2, hs:  104, trend: [8, 22, 30, 41, 28, 56, 33, 48, 90, 104] },
  { id: 4,  name: "Henry Vaughn",    runs:  674, avg: 33.7, sr: 92.5, hs:   88, trend: [15, 28, 9, 44, 22, 51, 18, 38, 62, 88] },
  { id: 5,  name: "Sam Okafor",      runs:  601, avg: 30.0, sr: 84.1, hs:   76, trend: [11, 18, 24, 33, 12, 41, 28, 36, 48, 76] },
];

export const mockTopWickets = [
  { id: 6,  name: "Asha Patel",     wickets: 42, avg: 17.4, econ: 4.12, best: "5/22", trend: [1, 2, 0, 3, 1, 4, 2, 3, 5, 4] },
  { id: 7,  name: "Marcus Lyle",    wickets: 38, avg: 19.2, econ: 4.85, best: "4/31", trend: [0, 2, 1, 3, 1, 2, 4, 1, 3, 4] },
  { id: 8,  name: "Dev Khanna",     wickets: 31, avg: 22.5, econ: 5.20, best: "4/18", trend: [1, 1, 0, 2, 2, 3, 1, 4, 2, 3] },
  { id: 9,  name: "Cole Rivers",    wickets: 28, avg: 23.7, econ: 5.05, best: "3/24", trend: [0, 1, 2, 1, 3, 0, 2, 4, 2, 3] },
  { id: 10, name: "Otto Brennan",   wickets: 24, avg: 26.1, econ: 5.42, best: "3/29", trend: [1, 0, 2, 1, 1, 3, 1, 2, 3, 2] },
];

export const mockUpcomingMilestones = [
  { id: 1,  name: "Jack Banner",   target: "1500 club runs", current: 1217, target_value: 1500, kind: "runs" },
  { id: 6,  name: "Asha Patel",    target: "50 club wickets", current: 42, target_value: 50,   kind: "wickets" },
  { id: 2,  name: "Tom Whitfield", target: "1000 club runs",  current: 984, target_value: 1000, kind: "runs" },
  { id: 3,  name: "Reggie Stone",  target: "1st century",     current: 812, target_value: 1000, kind: "milestone" },
];

export const mockRecentMatches = [
  { id: 901, date: "2026-05-09", opp: "Marlow CC",      result: "WIN",  format: "T20",  for: "187/4",  against: "164/8",  margin: "23 runs",  hero: "J. Banner 78 (42)" },
  { id: 902, date: "2026-05-02", opp: "Pinner CC",       result: "WIN",  format: "T20",  for: "201/6",  against: "172 a.o.", margin: "29 runs",  hero: "A. Patel 4/22" },
  { id: 903, date: "2026-04-26", opp: "Stoke Green CC",  result: "LOSS", format: "OD",   for: "212 a.o.", against: "215/7", margin: "3 wkts",   hero: "T. Whitfield 88 (94)" },
  { id: 904, date: "2026-04-19", opp: "Brentham CC",     result: "WIN",  format: "T20",  for: "166/3",  against: "142/9",  margin: "24 runs",  hero: "M. Lyle 3/19" },
  { id: 905, date: "2026-04-12", opp: "Ealing CC",       result: "WIN",  format: "OD",   for: "248/5",  against: "201 a.o.", margin: "47 runs",  hero: "J. Banner 102* (88)" },
  { id: 906, date: "2026-04-05", opp: "Wembley CC",      result: "DRAW", format: "OD",   for: "187/6",  against: "184/7",  margin: "—",        hero: "R. Stone 64 (71)" },
];

export const mockUpcomingFixtures = [
  { id: 1001, date: "2026-05-16", opp: "Harrow Town CC",   ground: "HOME",  format: "T20", time: "13:30" },
  { id: 1002, date: "2026-05-23", opp: "Ruislip CC",       ground: "AWAY",  format: "OD",  time: "11:00" },
  { id: 1003, date: "2026-05-30", opp: "Northwood CC",     ground: "HOME",  format: "T20", time: "13:30" },
];

// ── Player profile (matches /api/players/{id}) ─────────────────────────
export const mockPlayer = {
  id: 1,
  name: "Jack Banner",
  role: "TOP-ORDER BATTER",
  bat_hand: "RHB",
  bowl_hand: "RM",
  member_since: "2019",
  jersey: 17,
  career: {
    matches: 78,
    innings: 71,
    runs_scored: 2841,
    average: 46.6,
    strike_rate: 88.4,
    high_score: 142,
    centuries: 4,
    fifties: 18,
    fours: 312,
    sixes: 84,
    not_outs: 10,
  },
  season: {
    matches: 14,
    innings: 13,
    runs_scored: 1217,
    average: 52.9,
    strike_rate: 91.2,
    high_score: 142,
    centuries: 2,
    fifties: 6,
  },
  bowling_season: {
    overs: 28.4,
    wickets: 5,
    economy_rate: 5.42,
    best: "2/14",
  },
  recent_form: [78, 12, 142, 38, 64, 6, 102, 41, 28, 88, 16, 67, 22, 102],
  by_grade: [
    { grade: "1st XI", innings: 22, runs: 944, avg: 49.7, sr: 88.1 },
    { grade: "2nd XI", innings: 24, runs: 818, avg: 42.0, sr: 86.4 },
    { grade: "3rd XI", innings: 16, runs: 612, avg: 51.0, sr: 92.8 },
    { grade: "Cup",    innings:  9, runs: 467, avg: 58.4, sr: 95.1 },
  ],
  by_position: [
    { position: "Opener", innings: 32, runs: 1411, avg: 50.4, sr: 87.6 },
    { position: "No. 3",  innings: 24, runs:  988, avg: 47.0, sr: 89.9 },
    { position: "No. 4",  innings: 15, runs:  442, avg: 36.8, sr: 88.1 },
  ],
  dismissal_split: [
    { type: "Caught",   pct: 41 },
    { type: "Bowled",   pct: 22 },
    { type: "LBW",      pct: 14 },
    { type: "Run out",  pct:  8 },
    { type: "Stumped",  pct:  5 },
    { type: "Not out",  pct: 10 },
  ],
  upcoming_milestones: [
    { target: "1500 season runs", current: 1217, target_value: 1500 },
    { target: "3000 career runs", current: 2841, target_value: 3000 },
    { target: "5th century",      current: 4,    target_value: 5    },
  ],
  recent_innings: [
    { id: 901, date: "2026-05-09", opp: "Marlow CC",    score: "78 (42)",    sixes: 4, fours: 8, sr: 185.7, result: "WIN"  },
    { id: 902, date: "2026-05-02", opp: "Pinner CC",    score: "12 (14)",    sixes: 0, fours: 2, sr:  85.7, result: "WIN"  },
    { id: 903, date: "2026-04-26", opp: "Stoke G. CC",  score: "142 (118)",  sixes: 6, fours: 16, sr: 120.3, result: "LOSS" },
    { id: 904, date: "2026-04-19", opp: "Brentham CC",  score: "38 (28)",    sixes: 1, fours: 5, sr: 135.7, result: "WIN"  },
    { id: 905, date: "2026-04-12", opp: "Ealing CC",    score: "102* (88)",  sixes: 4, fours: 12, sr: 115.9, result: "WIN"  },
  ],
};

// ── tiny API helper with fallback ──────────────────────────────────────
// Use as: const summary = await fetchOrMock(api.club.summary, mockClubSummary);
export async function fetchOrMock(promise, mock) {
  try {
    const r = await promise;
    if (!r || (Array.isArray(r) && r.length === 0)) return mock;
    return r;
  } catch (e) {
    console.warn("[BetterStats] API failed, using mock:", e?.message);
    return mock;
  }
}
