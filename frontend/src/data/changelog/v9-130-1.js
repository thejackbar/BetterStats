export default {
  version: 'v9.130.1',
  date: '2026-10-26',
  // Above v9.130.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-09T05:00:00Z',
  title: 'Milestone watch on lineup posts, and Milestones settings out of the way',
  items: [
    'New: lineup posts can show who is about to reach a club milestone. A gold badge sits beside the player\'s name, and a Milestone watch strip above the foot lists up to three, for example "Sam Szigligeti — 40 runs to 1,000 club runs". The strip is left off the post entirely when nobody is close.',
    'New: the watch uses the same figures and increments as the Milestones page. A player in the XI on 49 games is flagged as playing their 50th, 99 as their 100th, and so on for the steps your club has set. Runs and wickets show when a player is within reach of the next one. A certain games milestone comes first, then the closest, one per player.',
    'New: it works on Hero List, Card Grid, Side Numbered, Team Sheet, Split Poster and Match Day Card, at every post size, including 12 names. The other lineup layouts say they do not draw it.',
    'New: figures are as of the last completed round. If a game from that round has not been scored yet, or the last sync finished before it was played, the post will not download or save to Club Room until you run a sync and press Check again, or switch Milestone watch off.',
    'Changed: on the Milestones page the settings for how often runs, wickets, matches and catches are marked, and the per grade ones, now sit at the bottom of the page, closed until you open them, so the milestones come first.',
  ],
}
