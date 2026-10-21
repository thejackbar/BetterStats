export default {
  version: 'v9.128.4.3',
  date: '2026-10-21',
  // Above v9.128.4.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-05T17:30:00Z',
  title: 'Fix: the daily update fixes its own drafts instead of being held back',
  items: [
    'When the morning note\'s first draft broke a rule, such as a headline a few characters too long after a big week of releases, the whole day was held back. It now sends the draft back with what was wrong and asks for a corrected one, up to three tries. A draft that still breaks a rule is held back, as before.',
  ],
}
