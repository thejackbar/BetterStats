export default {
  version: 'v9.113.3',
  date: '2026-10-19',
  sortKey: '2026-10-19T09:00:00Z',
  title: 'Sync also fills in a recent game\'s fall of wickets and partnerships',
  items: [
    'When sync goes back for a recent game that was stored without its detail, it now fills in the fall of wickets and the partnerships as well as the batting, bowling and fielding. A game stored without them showed an empty partnerships panel and added nothing to the partnership records.',
    'A game from the last 14 days that has no fall of wickets and no partnerships at all is now read again on every sync, up to 40 games a run, newest first. Rows are only added: an innings that already has fall of wickets or partnerships is left exactly as it is.',
  ],
}
