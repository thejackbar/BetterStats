export default {
  version: 'v9.93.0',
  date: '2026-09-30',
  // Above v9.92.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-09-30T12:00:00Z',
  title: 'Milestones count what the player’s profile counts, and show both figures when juniors are involved',
  items: [
    'Milestones in reach now use the same figures as each player’s profile. They used to leave out imported and hand-entered matches, so a bowler on 478 wickets could be listed as 3 short of 200.',
    'For a player who has played both junior and senior cricket, each milestone now shows the figure with their junior matches and the figure without them. If only one of the two is close to a milestone, that milestone is still listed and says which figure it is.',
    'The milestone emails carry both figures too, so a club doesn’t have to open the page to see which one applies.',
    'Stored milestones are now kept in line with the figures. A milestone the player hasn’t actually reached is removed, and one they did reach keeps its original date.',
    'A player’s own Milestones card on their profile uses the same figures.',
  ],
}
