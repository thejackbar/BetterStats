export default {
  version: 'v9.29.4',
  date: '2026-08-18',
  sortKey: '2026-08-25T16:00:00Z',
  title: 'StatLab: Grade type and Match type filters',
  items: [
    'StatLab now has the same two grade filters the rest of the site has. Grade type picks Men\'s, Juniors, Women\'s or Masters cricket; Match type picks Two Day, One Day or T20.',
    'Both are tick boxes, so a query can cover several at once: the Women\'s and Juniors grades together, or the T20s and one-dayers but not the two-day games.',
    'Match type is read off each fixture, not off the grade, so a grade that plays both formats in one season is split correctly instead of filed under one.',
    'StatLab also counts what the rest of the site counts now. It used to include every grade whatever the club had set, so a club that leaves juniors out of its stats saw StatLab disagree with the Leaderboard. Both read the club default from here on, and the Grade type control says what that default leaves out.',
    'A club is only offered the grade types and match types it actually runs, and the results say which grades are being left out so a figure is never quietly narrower than it looks.',
  ],
}
