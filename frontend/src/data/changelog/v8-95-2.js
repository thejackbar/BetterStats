export default {
  version: 'v8.95.2',
  date: '2026-07-30',
  sortKey: '2026-07-30T18:00:00Z',
  title: 'CRM: fix "Delete permanently" failing on a club with match data',
  items: [
    'Deleting a deal permanently with the "this was test activity. Also delete the club" option ticked no longer errors out. On a club that had synced games, it used to appear to do nothing and then show an Internal Server Error.',
    'The purge now clears the club\'s partnership, fall-of-wicket, bowler-wicket and milestone rows before removing the club, so the database can no longer trip over a leftover reference to an already-removed game.',
  ],
}
