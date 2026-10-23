export default {
  version: 'v9.129.11',
  date: '2026-10-23',
  // Above v9.129.10's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T23:55:00Z',
  title: 'Fantasy: Pick Squad no longer says you are a batter short when the counts look right',
  items: [
    'Pick Squad counted each player by the role saved when the squad was first picked, but the save is checked against the role the player has in the pool today. If a player had moved from batter to all-rounder since (a profile change, a pool rebuild or an admin override), the screen showed 4 of 4 batters while the save said "Need 4 batter(s), have 3. Need 3 allrounder(s), have 4." and nothing you changed would clear it.',
    'The role tiles, the squad list and the budget now read each player\'s current role and price from the pool, so what you see is what the save is checked against.',
  ],
}
