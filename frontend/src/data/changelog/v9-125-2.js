export default {
  version: 'v9.125.2',
  date: '2026-10-20',
  // Above v9.125.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-04T10:00:00Z',
  title: 'Fix: the server failed to start after the Card review doubles release',
  items: [
    'v9.125.1 stopped the server from starting. The new Card review filters were built in a way the server\'s own library version could not read, so it crashed while loading its routes and kept restarting. They are rebuilt in a form that version reads. The doubles step, Find a match and the filters on every step are otherwise as released in v9.125.1.',
  ],
}
