export default {
  version: 'v9.26.3',
  date: '2026-08-17',
  sortKey: '2026-08-19T06:00:00Z',
  title: 'A Won or Lost deal never shows up in the Sales Workspace queue',
  items: [
    'A deal created straight into the Won or Lost / Dormant stage could keep reading as an ordinary open deal, so it still showed up as something to call. The queue now checks the stage itself, not just that flag, so a deal that\'s already closed is excluded whichever way it got there.',
    'New deals created directly into a Won or Lost stage now have their own status set correctly from the moment they\'re created, instead of only when moved there afterwards.',
  ],
}
