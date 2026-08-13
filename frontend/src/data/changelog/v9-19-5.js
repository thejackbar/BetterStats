export default {
  version: 'v9.19.5',
  date: '2026-08-11',
  // Must sort above v9.19.4.2's (future-dated) 2026-08-15T20:00:00Z key,
  // or SITE_VERSION keeps reading v9.19.4.2.
  sortKey: '2026-08-15T21:00:00Z',
  title: 'Edit and delete seasons',
  items: [
    'Every row on Admin → Seasons now has an Edit button, so a season\'s name or year can be fixed in place. A renamed season keeps its new name across future syncs.',
    'Manually-created seasons can be deleted from the same page. Only an empty season is accepted: anything with games, grades or stats recorded against it is refused with the reason, so a season full of imported history can never be removed by accident.',
  ],
}
