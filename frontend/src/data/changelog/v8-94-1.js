export default {
  version: 'v8.94.1',
  date: '2026-07-29',
  sortKey: '2026-07-30T04:00:00Z',
  title: 'Fixtures and Lineups: real Category and Finals filters, and click-through between the two pages',
  items: [
    'Removed the taglines under "What\'s coming up" and "Who\'s playing" — the page titles already say what they are.',
    'The Lineups page\'s Category filter (Senior, Junior, Women\'s, and so on) and Finals filter now actually work — they used to sit there doing nothing.',
    'Category is based on how each grade is classified at your club, not a per-player attribute, so it lines up with the same Senior/Junior/Women\'s split used elsewhere on the site.',
    'The captain filter was removed from Lineups — it never meant anything there.',
    'A played match\'s lineup card now links straight to its full scorecard.',
    'A fixture\'s "Lineup" link now opens that exact game\'s lineup, instead of the general Lineups list.',
  ],
}
