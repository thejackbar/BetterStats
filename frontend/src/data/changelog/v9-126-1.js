export default {
  version: 'v9.126.1',
  date: '2026-10-20',
  // Above v9.126.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-04T16:00:00Z',
  title: 'Match fees are charged the day after the game',
  items: [
    'A game is now added to match fees from the day after it was played, not on the day. If a game is moved after it has been scored, nobody is charged for the wrong day.',
    'If a game that already has an unpaid match fee is moved to a later date, the fee is taken off until that day has passed. A fee that has been paid is never removed.',
    'The day rolls over at midnight Perth time, so a club on the east coast sees the charge appear a few hours after midnight.',
  ],
}
