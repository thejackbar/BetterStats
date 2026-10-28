export default {
  version: 'v9.134.1',
  date: '2026-10-28',
  // Above v9.134.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-11T12:30:00Z',
  title: 'Games between two of your own teams now count for both sides',
  items: [
    'When two of your teams played each other (Applecross Red v Applecross Pink, say), only one side was stored. The other side\'s players got no batting, bowling or fielding for that game, and it did not count in their match total. Both sides are now stored.',
    'Shaylyn Wijesinghe is the case that showed it: Cricket Australia lists 98 games for her, and six of the ones we were missing were games between two Applecross teams.',
    'A Full Rebuild fixes games already stored one-sided. An ordinary sync also adds the missing side to a game it has already stored, and leaves the side it holds alone.',
  ],
}
