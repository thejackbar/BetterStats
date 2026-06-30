export default {
  version: 'v8.43.20.1',
  date: '2026-06-30',
  sortKey: '2026-06-30T09:00:00Z',
  title: 'Fix "Something went wrong" on retired or unknown club pages',
  items: [
    'Visiting a club page for a slug that is no longer active (for example an old association link) showed a "Something went wrong" crash instead of the "club not available" screen. The page now falls through to that screen as intended. The same fix covers the club dashboard, players, leaderboard, records, games and StatLab pages.',
  ],
}
