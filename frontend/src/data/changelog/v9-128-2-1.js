export default {
  version: 'v9.128.2.1',
  date: '2026-10-20',
  // Above v9.128.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-05T14:30:00Z',
  title: 'Fix: the server build failed after the teaser pictures release',
  items: [
    'The backend image could not be built because the picture renderer\'s library needed a newer greenlet than the rest of the app pins. It now uses a version that fits, so the build completes and the rest of the app is unchanged.',
    'The renderer now starts Chrome in the headless mode current Chrome versions still support, so Draw pictures works with the Chrome the backend image installs.',
  ],
}
