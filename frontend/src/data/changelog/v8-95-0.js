export default {
  version: 'v8.95.0',
  date: '2026-07-30',
  sortKey: '2026-07-30T14:00:00Z',
  title: 'Usage page: Current Background Processes, and self-healing syncs',
  items: [
    'The Super Admin Usage page has a new "Current Background Processes" section above the live traffic. It lists what the platform is working on right now: Full Rebuilds and syncs (with the club, who started them, how long they have been going and a live percentage), BetterIQ opponent prewarms, self-serve registrations still in progress (and which step the prospect is up to), and clubs actively working the Setup Wizard.',
    'Long-running syncs now heal themselves. If the backend restarts while a Full Rebuild or Sync is mid-run, that job is automatically restarted on startup and picks up where it left off, instead of being left half-finished.',
    'Sync runs now record which admin started them, so the new panel can show who kicked off each job.',
  ],
}
