export default {
  version: 'v9.106.5.1',
  date: '2026-10-05',
  // Above v9.106.5's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-05T02:00:00Z',
  title: 'The weekend sync no longer skips a round when grades are added after the season starts',
  items: [
    'Some clubs played their first round of the season and the Sunday and Monday syncs both reported "No fixtures played, nothing to pull". The results were on Cricket Australia the whole time. The sync only looked at the grades we already held for the season, and a club\'s A to I Grade teams are often added after the season first appears, once the draw is made. It now checks the club\'s teams on Cricket Australia too, and a grade it has not seen yet triggers a normal sync that adds the grade and pulls its results.',
    'The list of fixtures we keep for each grade is now refreshed every half hour. Before, it was kept until the next update of the app, so a round published after we first looked could stay hidden from syncs, BetterIQ and social posts.',
    'If a club is missing a weekend\'s results, press Quick Sync on the Sync page. It covers the last seven days.',
  ],
}
