export default {
  version: 'v8.43.0',
  date: '2026-06-29',
  sortKey: '2026-06-29T01:00:00Z',
  title: 'Export the Clubs Directory to the Twenty CRM',
  items: [
    'Super admins can push the currently-filtered Clubs Directory selection into the Twenty CRM from the directory page. It sends each matched club, its association and its officers as Companies, Associations and People, so the sales pipeline lives in one place.',
    'The export is opt-in and idempotent: only the clubs you filter to are sent, and re-running updates existing records and skips unchanged ones rather than duplicating. The directory stays the full list; Twenty holds the targeted subset.',
  ],
}
