export default {
  version: 'v8.60.4',
  date: '2026-07-14',
  sortKey: '2026-07-14T16:00:00Z',
  title: 'Fixed: a Super Admin stayed "acting as" a club after archiving it',
  items: [
    'Archiving a club a Super Admin was currently acting as left the "MANAGING X AS SUPER ADMIN" banner showing that club, even though it had dropped off the All Clubs list and the club switcher: the club row still exists after a soft-delete, so the usual "acted-as club is gone" fallback never noticed.',
    'Acting as a club now falls back to your home club the moment that club is archived, the same way it already did when a club was hard-deleted. Archiving a club you\'re currently acting as also switches you back to your home club straight away.',
  ],
}
