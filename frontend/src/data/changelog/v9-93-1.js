export default {
  version: 'v9.93.1',
  date: '2026-09-30',
  sortKey: '2026-09-30T18:00:00Z',
  title: 'A milestone a player reached with their junior matches is kept',
  items: [
    'Tidying up stored milestones now keeps any milestone the player has reached counting all their matches, junior games included. Before this fix, a milestone could be removed if it was only reached with junior matches, or if it was only reached on Cricket Australia’s career total and not on the scorecards we hold.',
    'Milestones that no count of the player’s matches reaches, such as a 500 wickets milestone for a bowler on 478, are still removed.',
  ],
}
