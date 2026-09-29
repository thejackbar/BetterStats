export default {
  version: 'v9.90.3',
  date: '2026-09-24',
  sortKey: '2026-09-30T05:00:00Z',
  title: 'A re-sourced season no longer drops the matches your file left out',
  items: [
    'When an import takes over some of a season from Cricket Australia, the matches it did not cover now still count from their own scorecards. Before this, the whole season\'s Cricket Australia totals stepped aside, so a player\'s "All" figure could read lower than their "Men\'s" one.',
    'The import now recognises a match you already have on its scorecard as well as its date and opponent, so a two-day match the two sources date a week apart, an opponent spelt differently, or a fixture the other club synced first is paired instead of counted twice. The review says how many were matched this way.',
    'Re-importing a file over an earlier overwrite import keeps each match paired to the Cricket Australia game it took over, rather than bringing the synced copy back beside it.',
  ],
}
