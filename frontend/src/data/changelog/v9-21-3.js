export default {
  version: 'v9.21.3',
  date: '2026-08-13',
  sortKey: '2026-08-16T15:00:00Z',
  title: 'BetterFootball: creating a user could 500',
  items: [
    'Better HQ → Users (platform) could fail with a bare "Internal Server Error" when creating, renaming or resetting a user. Any malformed or stale club/user id now gets a clear message instead of crashing the request.',
    'Creating a user is more resilient to a genuine database hiccup (e.g. a racing duplicate username). It now reports what actually went wrong rather than a generic server error.',
  ],
}
