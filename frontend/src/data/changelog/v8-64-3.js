export default {
  version: 'v8.64.3',
  date: '2026-07-15',
  sortKey: '2026-07-15T08:00:00Z',
  title: 'Dashboard module tiles show real status, and a trial-expiry date bug fixed',
  items: [
    'A subscribed or trialling module tile on the Dashboard now shows its status and date (Subscribed · renews X, or Trial · ends X), the same data the Account page shows.',
    'The Dashboard\'s "Subscribe" link now reads SUBSCRIBE, matching START TRIAL.',
    'The Dashboard no longer shows a START TRIAL button for a module that already had its one trial (it silently failed before: now it\'s just not offered, and a genuine error shows inline if starting one ever does fail).',
    'Fixed a bug where the Account page could show a module as "Trial Expired · ended" a date that was still in the future. That happened when a trial had been cancelled early rather than actually running out; the leftover end date is no longer shown once it no longer means anything.',
  ],
}
