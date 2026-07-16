export default {
  version: 'v8.66.3',
  date: '2026-07-15',
  sortKey: '2026-07-15T15:00:00Z',
  title: 'Fixed "Unknown module(s): core" on checkout',
  items: [
    'Selecting BetterStats itself (not just an add-on module) on the Account page and proceeding to checkout was rejected with "Unknown module(s): core". BetterStats is always included in the price automatically, so it now passes straight through instead of being treated as an unrecognised selection.',
  ],
}
