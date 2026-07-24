export default {
  version: 'v8.80.1',
  date: '2026-07-24',
  sortKey: '2026-07-24T15:00:00Z',
  title: 'Upload Scorecard: choose what the card tracks, smarter player matching',
  items: [
    'A new "This card tracks" panel on the review screen lets you untick fields the card simply doesn\'t record (balls faced, 4s and 6s, maidens, bowler wides and no-balls). Unticked fields are hidden from the review tables and import as "not recorded" instead of a zero, so an old summary card never drags a player\'s boundary or discipline stats down with fake zeroes. The reader pre-ticks based on what it actually found on the card.',
    'Player matching on the review screen now uses the same fuzzy engine as historical imports and Merge Players: exact names auto-match, "G Evans" style scorecard names auto-fill when only one player fits, and near-miss spellings ("Malcom" for "Malcolm") appear as one-click close matches with a confidence score at the top of each player picker.',
  ],
}
