export default {
  version: 'v8.60.7',
  date: '2026-07-14',
  sortKey: '2026-07-14T19:00:00Z',
  title: 'Fixed a silent error on every notification bell poll',
  items: [
    'The bell icon\'s 60-second badge poll was quietly failing every time and falling back to a zero count, because it was reading a user\'s role from the wrong place. It now reads the correct membership role, so pending reports and other role-gated notifications count properly again.',
  ],
}
