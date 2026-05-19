// Sample data — in production this is what your DB shape would look like
// Plug your fields into these objects; the templates read from `team`, `opponent`, `match`, `players`.

window.SAMPLE_TEAM = {
  name: "NORTHGATE",
  city: "NORTHGATE",
  short: "NGC",
  // Two-letter monogram used in the "club logo" placeholder. Replace with a real <img>.
  monogram: "NG",
};

window.SAMPLE_OPPONENT = {
  name: "EASTSIDE",
  short: "ESX",
  monogram: "ES",
};

window.SAMPLE_MATCH = {
  competition: "PREMIER T20",
  round: "ROUND 7",
  venue: "Heathcote Reserve",
  date: "SAT 30 MAY",
  time: "2:30 PM",
  season: "2025–26",
};

// Companion-template sample data
window.SAMPLE_TOSS = {
  winner: "TEAM",          // "TEAM" | "OPPONENT"
  decision: "BAT",         // "BAT" | "BOWL"
};

window.SAMPLE_MOTM = {
  player: { first: "Marcus", last: "HOLT", role: "BAT", roleLong: "Top-Order Batter", headshot: "assets/player-cutout.png" },
  stats: [
    { label: "Runs",   value: "87" },
    { label: "Balls",  value: "54" },
    { label: "Fours",  value: "9"  },
    { label: "Sixes",  value: "4"  },
    { label: "Strike Rate", value: "161.1" },
    { label: "Not Out", value: "★" },
  ],
  summary: "Anchored the chase with a match-winning 87* off 54, his fourth fifty of the season.",
};

window.SAMPLE_RESULT = {
  winner: "TEAM",          // "TEAM" | "OPPONENT" | "TIE"
  margin: "by 28 runs",    // result margin text
  teamScore: "182/6 (20)",
  oppScore: "154/9 (20)",
  motmLast: "HOLT",
};

// Sample 13-player squad. Templates that need 11 use the first 11.
// role values used by the templates: BAT, BOWL, AR, WK
// `headshot` is optional — a transparent-bg cutout. If missing, templates
// fall back to the club logo (or the team monogram).
window.SAMPLE_PLAYERS = [
  { first: "Marcus",  last: "HOLT",       role: "BAT",  roleLong: "Top-Order Batter",  captain: true,        headshot: "assets/player-cutout.png" },
  { first: "Devansh", last: "RAO",        role: "BAT",  roleLong: "Top-Order Batter",  viceCaptain: true },
  { first: "Tomas",   last: "VEGA",       role: "WK",   roleLong: "Wicket-Keeper",     keeper: true },
  { first: "Eli",     last: "HARTMAN",    role: "AR",   roleLong: "All-Rounder" },
  { first: "Jared",   last: "NGATA",      role: "AR",   roleLong: "All-Rounder" },
  { first: "Reuben",  last: "COLE",       role: "BAT",  roleLong: "Middle Order" },
  { first: "Sam",     last: "WHITFIELD",  role: "BOWL", roleLong: "Right-Arm Pace" },
  { first: "Owen",    last: "STRATTON",   role: "BOWL", roleLong: "Off-Spin" },
  { first: "Kade",    last: "LINWOOD",    role: "BOWL", roleLong: "Left-Arm Pace" },
  { first: "Ari",     last: "BEKELE",     role: "AR",   roleLong: "All-Rounder" },
  { first: "Felix",   last: "MARO",       role: "BOWL", roleLong: "Leg-Spin" },
  { first: "Joaquin", last: "PERALTA",    role: "BAT",  roleLong: "Middle Order" },
  { first: "Lior",    last: "ASHKENAZI",  role: "BOWL", roleLong: "Right-Arm Pace" },
];

// Color palettes — picked to read as "team kit" not "AI default". All bold and gritty.
window.PALETTES = {
  midnight: { name: "Midnight",  primary: "#0b1530", secondary: "#1a2647", accent: "#ffc233", ink: "#ffffff" },
  crimson:  { name: "Crimson",   primary: "#2a0a0e", secondary: "#5a0f1a", accent: "#ff3344", ink: "#fff4e6" },
  forest:   { name: "Forest",    primary: "#0c2418", secondary: "#163828", accent: "#c4ff4d", ink: "#f4fbe8" },
  cobalt:   { name: "Cobalt",    primary: "#0b1f4a", secondary: "#17336b", accent: "#00c2ff", ink: "#ffffff" },
  rust:     { name: "Rust",      primary: "#1e0f08", secondary: "#3a1a0a", accent: "#ff7a1a", ink: "#fff1e3" },
  graphite: { name: "Graphite",  primary: "#101113", secondary: "#1d1f23", accent: "#e8ff00", ink: "#ffffff" },
};
