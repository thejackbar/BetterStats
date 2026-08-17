export default {
  version: 'v9.28.0',
  date: '2026-08-17',
  sortKey: '2026-08-24T03:00:00Z',
  title: 'Grade Type and Match Type on every stats page',
  items: [
    'The Leaderboard, Club Records, Players and Games pages now have the same Grade Type and Match Type filters as the club dashboard. Filter the batting leaderboard to the women\'s grades, or the club records to two-day cricket, and every board on the page follows.',
    'Player profiles get them too, and they move the whole profile — the career figures, the season-by-season table, and every panel under Analysis (by grade, by position, by venue, by opposition, dismissals, partnerships and the bowling breakdowns). A profile filtered to T20 no longer has a by-venue panel quietly counting two-day games.',
    'One control everywhere. The older "Include" row, which added juniors on top of the seniors, is gone in favour of the pick-one Grade Type row that answers the same question more directly.',
    'The Games list now shows each match\'s format, so you can see at a glance which fixtures in a grade were two-day and which were one-day.',
    'Fixed: the by-grade panels on a player profile counted every innings in a grade that sometimes plays two-day cricket as two-day. They read each match\'s own format now, like everything else.',
    'Asking for a format you have never played gives you an empty page rather than quietly widening to something else — if a player has no T20 record, that is the answer.',
  ],
}
