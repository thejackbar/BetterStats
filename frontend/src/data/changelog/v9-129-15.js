export default {
  version: 'v9.129.15',
  date: '2026-10-24',
  // Above v9.129.14's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T02:00:00Z',
  title: 'Match page: a score is shown under the side that batted',
  items: [
    'Fixed: when only one side batted in a match (a drawn two-day game, for example), the match page header showed that innings under the home team whichever side it belonged to. Payneham 3 v Eastern Suburbs 2, where only Eastern Suburbs batted, showed Eastern Suburbs\' 320 and crest under Payneham 3. The score now appears under the side that batted, as it already did when both sides had an innings.',
  ],
}
