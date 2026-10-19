export default {
  version: 'v9.122.2',
  date: '2026-10-25',
  // Above v9.122.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T03:00:00Z',
  title: 'Two-day games ask which weeks a player can do, and every screen shows it the same way',
  items: [
    'Tapping a player\'s dot on the Squads board for a two-day game now opens a window with four quick answers: Both weeks, W1 Only, W2 Only and Not available. Each one saves both weeks at once. The week rows underneath are still there for a Maybe or a different answer each week.',
    'The Squads board reads a two-day game on both weeks. The column says it is a two-day game and names both dates, and a player\'s card takes the least favourable week, the same as the Selection board.',
    'The player\'s own availability page has the same four answers on its two-day card, so a player in a one-day side answers both weeks of a two-day game too. Everyone on the link is asked about every game.',
    'One tag now means the same thing on the Squads board, the Selection board and the Selection Whiteboard. "W2 ONLY" means free for week 2 and away for week 1, and is drawn in that week\'s half-available colour. "W1 OUT" means away for week 1 with no yes for week 2, in red. "W2 ?" means a maybe, in amber. The tag is always the colour of the card\'s own dot and edge, so the same words never come in two colours. Before, a player away in week 1 and free in week 2 and a player away in week 1 with no answer for week 2 both read "W1 OUT" in different colours.',
    'In Settings under Two-day games you can name the two weeks. A club that calls them A and B sees "A Only", "B OUT" and "B ?" everywhere, including the player\'s own page and the Availability screen. Blank goes back to W1 and W2.',
    'Week 1 Only and Week 2 Only are now called W1 Only and W2 Only. The Selection board\'s long "Week 1 Available · Week 2 Unavailable" line is replaced by the same tag.',
  ],
}
