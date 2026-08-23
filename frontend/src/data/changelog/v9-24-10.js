export default {
  version: 'v9.24.10',
  date: '2026-08-15',
  sortKey: '2026-08-15T09:30:00Z',
  title: 'Fix Sales role login blocked by an inactive outreach org',
  items: [
    'A Sales-role account could not log in, "Club is not active", because a Sales user is pinned to the platform\'s internal outreach org, which was never marked active like a real subscribing club. Login now exempts the Sales role from that check, the same way it already exempts Super Admin.',
  ],
}
