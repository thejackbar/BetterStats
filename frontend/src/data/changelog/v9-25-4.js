export default {
  version: 'v9.25.4',
  date: '2026-08-17',
  sortKey: '2026-08-19T04:00:00Z',
  title: 'A viewed club\'s engagement score corrects itself, and the drawer gets website analytics',
  items: [
    'A club\'s engagement score could go stale and stay stale: it\'s only ever refreshed by a nightly job that skips any club not yet pushed to Twenty, so a score set once (e.g. a direct enquiry\'s one-time Hot 100) could keep showing on the card long after the real number had moved on, while the detail panel next to it quietly showed the true figure. Opening that panel now corrects the stored score too, so the card and queue row catch up on their next load instead of drifting forever.',
    'The Sales Workspace drawer gets its own Website analytics card: page views, days visited, unique IPs and whether the contact page was hit, the same figures the Sales Pipeline card already shows.',
  ],
}
