export default {
  version: 'v8.77.3',
  date: '2026-07-22',
  sortKey: '2026-07-22T15:00:00Z',
  title: 'Club merger tool: fixed vanishing player stats and a former club showing up as its own opponent',
  items: [
    'A player whose whole career sat under a merged-in predecessor club (e.g. a real-world club amalgamation done through the club merger tool) could show zero stats on their summary page while the same stats were still visible elsewhere. The merger tool now correctly repoints a player\'s season and grade stats when the two clubs shared the same competition, instead of leaving them attached to the old, archived club record. A one-off repair tool has been added for clubs already merged before this fix, under Super Admin → Merge clubs.',
    'After a club merger, the absorbed club could still show up as one of "our" opponents in BetterIQ\'s Opposition list, since old fixtures between the two clubs (from before they merged) kept referencing the now-absorbed club by name. Those are no longer listed as a scoutable opponent.',
    'Opponent names picked up from a scorecard are now normalised the same way our own team names already are, so the same club no longer shows up as several separate entries in the opposition list split by grade or team number (e.g. "2nd XI").',
  ],
}
