export default {
  version: 'v9.134.3',
  date: '2026-10-28',
  // Above v9.134.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-11T13:30:00Z',
  title: 'Sync page: Clean Opposition Stats is gone, Fix Missing Totals moves under Repairs',
  items: [
    'The Clean Opposition Stats button is removed. It was a one-off for an old bug where a player who played against you had those games counted as theirs. Sync no longer does that, and a Full Rebuild puts everything right if you ever see it.',
    'Fix Missing Totals now sits under a collapsed Repairs heading. Sync already rebuilds those totals after any run that adds games, so you should rarely need it. It still works if a player shows 0 matches despite having innings.',
  ],
}
