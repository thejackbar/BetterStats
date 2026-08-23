export default {
  version: 'v9.23.2.3',
  date: '2026-08-14',
  sortKey: '2026-08-14T15:00:00Z',
  title: 'A player’s Analysis tab ignored the Junior/Senior filter entirely',
  items: [
    'The "Batting by grade", "Bowling by grade", dismissal breakdowns, by-position, by-venue, by-opposition and partnership tables on a player\'s Analysis tab always showed every grade the player has ever turned out in, including Juniors, no matter what the Junior/Senior toggle above the career figures was set to.',
    'Every one of those tables now honours the same category selection the career totals do, so switching Juniors off (or on) updates the whole page consistently, not just the headline numbers.',
  ],
}
