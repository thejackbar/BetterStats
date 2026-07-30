export default {
  version: 'v8.97.1',
  date: '2026-07-31',
  sortKey: '2026-07-31T01:00:00Z',
  title: 'Usage: idle limits for registrations and onboarding',
  items: [
    'The Current Background Processes panel on the Usage page has a new Settings button, next to Pause and Refresh.',
    'Settings has two idle limits, one for registrations in progress and one for clubs working the Setup Wizard. If a prospect or club sits at a step longer than its limit, it is treated as abandoned and drops off the panel.',
    'The one exception is a club whose first full rebuild is still running. That sync runs in the background after the admin leaves the page, so the club is kept on the list while the rebuild is going, and it already shows under Data syncs & rebuilds too.',
  ],
}
