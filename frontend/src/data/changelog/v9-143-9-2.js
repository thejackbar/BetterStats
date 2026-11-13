export default {
  version: 'v9.143.9.2',
  date: '2026-11-13',
  // Above v9.143.9.1's sortKey (2026-11-20T13:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T14:00:00Z',
  title: 'Upload Scorecard: add a bowler the reader missed',
  items: [
    "When you check a scorecard after it has been read, each innings now has an Add bowler button under its bowling figures. A scorer who runs out of analysis rows and writes the 9th and 10th bowler in the unused part of the grid can now have those two imported: add the row, pick the player and type their overs, maidens, runs and wickets.",
    "Each bowling row also has a small cross to remove it, for a bowler the reader made up or read twice.",
    "An innings where the reader found no bowlers at all used to show no bowling table, so there was nothing to add to. It now says no bowlers were read and offers the same button.",
    "A row you add but never match to one of our players is counted in the \"rows aren't matched\" warning and is left out of the import, the same as any other unmatched row.",
  ],
}
