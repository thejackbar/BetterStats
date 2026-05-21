// Full match scorecard sample data — 2023 ICC Cricket World Cup Final
// India 240 (50.0) vs Australia 241/4 (43.0). Australia won by 6 wickets.
// Narendra Modi Stadium, Ahmedabad. 19 November 2023. Player of the Match: Travis Head (137).

window.SAMPLE_FULL_MATCH = {
  meta: {
    competition: "ICC CRICKET WORLD CUP",
    round: "FINAL",
    format: "ODI",                       // ODI | T20 | TEST
    overs: 50,
    venue: "Narendra Modi Stadium, Ahmedabad",
    date: "SUN 19 NOV 2023",
    toss: "INDIA WON THE TOSS · ELECTED TO BAT",
    result: "AUSTRALIA WON BY 6 WICKETS",
    series: "ICC WORLD CUP 2023 · FINAL",
    motm: { first: "Travis", last: "HEAD", team: "AUS", line: "137 (120) · 1/14 from 2 overs" },
  },

  // Home team (battling first) — INDIA
  home: {
    name: "INDIA",
    short: "IND",
    color: "#1a4eb8",                    // royal blue
    logo: null,                          // we'll fall back to monogram shield
    monogram: "IND",
    total: "240",
    overs: "50.0",
    wickets: 10,
    runRate: "4.80",
    batting: [
      { num: 1,  first: "Rohit",       last: "SHARMA",     r: 47, b: 31,  fours: 4, sixes: 3, sr: 151.61, out: "c Maxwell b Cummins" },
      { num: 2,  first: "Shubman",     last: "GILL",       r: 4,  b: 7,   fours: 0, sixes: 0, sr: 57.14,  out: "c Zampa b Starc" },
      { num: 3,  first: "Virat",       last: "KOHLI",      r: 54, b: 63,  fours: 4, sixes: 0, sr: 85.71,  out: "b Cummins" },
      { num: 4,  first: "Shreyas",     last: "IYER",       r: 4,  b: 3,   fours: 1, sixes: 0, sr: 133.33, out: "c Inglis b Cummins" },
      { num: 5,  first: "KL",          last: "RAHUL",      r: 66, b: 107, fours: 1, sixes: 0, sr: 61.68,  out: "c Inglis b Starc", role: "WK" },
      { num: 6,  first: "Suryakumar",  last: "YADAV",      r: 18, b: 28,  fours: 1, sixes: 0, sr: 64.29,  out: "c Inglis b Hazlewood" },
      { num: 7,  first: "Ravindra",    last: "JADEJA",     r: 9,  b: 22,  fours: 0, sixes: 0, sr: 40.91,  out: "run out (Labuschagne)" },
      { num: 8,  first: "Mohammed",    last: "SHAMI",      r: 6,  b: 10,  fours: 1, sixes: 0, sr: 60.00,  out: "b Maxwell" },
      { num: 9,  first: "Jasprit",     last: "BUMRAH",     r: 1,  b: 3,   fours: 0, sixes: 0, sr: 33.33,  out: "c Inglis b Starc" },
      { num: 10, first: "Kuldeep",     last: "YADAV",      r: 10, b: 18,  fours: 0, sixes: 0, sr: 55.56,  out: "c Maxwell b Hazlewood" },
      { num: 11, first: "Mohammed",    last: "SIRAJ",      r: 9,  b: 8,   fours: 1, sixes: 0, sr: 112.50, out: "not out" },
    ],
    extras: { total: 15, b: 0, lb: 6, nb: 0, wd: 9 },
    fow: [
      { score: 30,  wkt: 1,  bat: "Gill",     over: "4.2" },
      { score: 76,  wkt: 2,  bat: "Rohit",    over: "9.4" },
      { score: 81,  wkt: 3,  bat: "Iyer",     over: "10.2" },
      { score: 148, wkt: 4,  bat: "Kohli",    over: "28.3" },
      { score: 178, wkt: 5,  bat: "Rahul",    over: "37.1" },
      { score: 192, wkt: 6,  bat: "Surya",    over: "41.3" },
      { score: 203, wkt: 7,  bat: "Jadeja",   over: "44.1" },
      { score: 211, wkt: 8,  bat: "Shami",    over: "46.4" },
      { score: 214, wkt: 9,  bat: "Bumrah",   over: "47.3" },
      { score: 240, wkt: 10, bat: "Kuldeep",  over: "49.6" },
    ],
    partnerships: [
      { wkt: 1,  runs: 30,  pair: "Rohit / Gill" },
      { wkt: 2,  runs: 46,  pair: "Rohit / Kohli" },
      { wkt: 3,  runs: 5,   pair: "Kohli / Iyer" },
      { wkt: 4,  runs: 67,  pair: "Kohli / Rahul" },
      { wkt: 5,  runs: 30,  pair: "Rahul / Surya" },
      { wkt: 6,  runs: 14,  pair: "Surya / Jadeja" },
      { wkt: 7,  runs: 11,  pair: "Jadeja / Shami" },
      { wkt: 8,  runs: 8,   pair: "Shami / Bumrah" },
      { wkt: 9,  runs: 3,   pair: "Bumrah / Kuldeep" },
      { wkt: 10, runs: 26,  pair: "Kuldeep / Siraj" },
    ],
    // Bowling figures for THIS team's bowling — i.e. India bowled to Australia
    bowling: [
      { first: "Jasprit",    last: "BUMRAH", o: 9,  m: 2, r: 43, w: 2, econ: 4.77 },
      { first: "Mohammed",   last: "SHAMI",  o: 7,  m: 1, r: 47, w: 1, econ: 6.71 },
      { first: "Mohammed",   last: "SIRAJ",  o: 7,  m: 0, r: 45, w: 1, econ: 6.42 },
      { first: "Kuldeep",    last: "YADAV",  o: 10, m: 0, r: 56, w: 0, econ: 5.60 },
      { first: "Ravindra",   last: "JADEJA", o: 9,  m: 0, r: 43, w: 0, econ: 4.77 },
      { first: "Suryakumar", last: "YADAV",  o: 1,  m: 0, r: 1,  w: 0, econ: 1.00 },
    ],
  },

  // Away team — AUSTRALIA
  away: {
    name: "AUSTRALIA",
    short: "AUS",
    color: "#ffcc00",                    // gold
    logo: null,
    monogram: "AUS",
    total: "241",
    overs: "43.0",
    wickets: 4,
    runRate: "5.60",
    batting: [
      { num: 1,  first: "David",       last: "WARNER",       r: 7,   b: 3,   fours: 1, sixes: 0, sr: 233.33, out: "c KL Rahul b Shami" },
      { num: 2,  first: "Travis",      last: "HEAD",         r: 137, b: 120, fours: 15, sixes: 4, sr: 114.17, out: "c Suryakumar b Siraj" },
      { num: 3,  first: "Mitchell",    last: "MARSH",        r: 15,  b: 15,  fours: 1, sixes: 1, sr: 100.00, out: "c KL Rahul b Bumrah" },
      { num: 4,  first: "Steven",      last: "SMITH",        r: 4,   b: 9,   fours: 0, sixes: 0, sr: 44.44,  out: "lbw b Bumrah" },
      { num: 5,  first: "Marnus",      last: "LABUSCHAGNE",  r: 58,  b: 110, fours: 4, sixes: 0, sr: 52.73,  out: "not out", notOut: true },
      { num: 6,  first: "Glenn",       last: "MAXWELL",      r: 2,   b: 1,   fours: 0, sixes: 0, sr: 200.00, out: "not out", notOut: true },
      { num: 7,  first: "Josh",        last: "INGLIS",       didNotBat: true, role: "WK" },
      { num: 8,  first: "Mitchell",    last: "STARC",        didNotBat: true },
      { num: 9,  first: "Pat",         last: "CUMMINS",      didNotBat: true, role: "C" },
      { num: 10, first: "Adam",        last: "ZAMPA",        didNotBat: true },
      { num: 11, first: "Josh",        last: "HAZLEWOOD",    didNotBat: true },
    ],
    extras: { total: 18, b: 2, lb: 4, nb: 0, wd: 12 },
    fow: [
      { score: 16,  wkt: 1, bat: "Warner",       over: "1.4" },
      { score: 41,  wkt: 2, bat: "Marsh",        over: "6.4" },
      { score: 47,  wkt: 3, bat: "Smith",        over: "9.5" },
      { score: 239, wkt: 4, bat: "Head",         over: "42.5" },
    ],
    partnerships: [
      { wkt: 1, runs: 16,  pair: "Warner / Head" },
      { wkt: 2, runs: 25,  pair: "Head / Marsh" },
      { wkt: 3, runs: 6,   pair: "Head / Smith" },
      { wkt: 4, runs: 192, pair: "Head / Labuschagne" },
      { wkt: 5, runs: 2,   pair: "Labuschagne / Maxwell", notOut: true },
    ],
    // Australia bowled to India
    bowling: [
      { first: "Mitchell", last: "STARC",     o: 10, m: 0, r: 55, w: 3, econ: 5.50 },
      { first: "Josh",     last: "HAZLEWOOD", o: 10, m: 2, r: 60, w: 2, econ: 6.00 },
      { first: "Glenn",    last: "MAXWELL",   o: 6,  m: 0, r: 35, w: 1, econ: 5.83 },
      { first: "Pat",      last: "CUMMINS",   o: 10, m: 0, r: 34, w: 2, econ: 3.40 },
      { first: "Adam",     last: "ZAMPA",     o: 10, m: 0, r: 44, w: 0, econ: 4.40 },
      { first: "Marcus",   last: "STOINIS",   o: 3,  m: 0, r: 7,  w: 0, econ: 2.33 },
      { first: "Travis",   last: "HEAD",      o: 2,  m: 0, r: 4,  w: 0, econ: 2.00 },
    ],
  },
};
