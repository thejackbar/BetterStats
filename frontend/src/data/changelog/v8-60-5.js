export default {
  version: 'v8.60.5',
  date: '2026-07-14',
  sortKey: '2026-07-14T17:00:00Z',
  title: 'Fixed: deleting a Super Admin user could silently fail',
  items: [
    'A user with a linked player profile couldn\'t be deleted from Super Admin > Users — the delete looked like it did nothing, no error shown. The database was quietly rejecting it and rolling back the whole thing.',
    'Fixed the underlying constraint so deleting a user account no longer gets blocked by that unused link.',
  ],
}
