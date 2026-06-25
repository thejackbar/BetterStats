export default {
  version: 'v8.28.1.1',
  date: '2026-06-25',
  sortKey: '2026-06-25T14:00:00Z',
  title: 'Partnership delete fix and faster Records pages',
  items: [
    'Deleting a partnership record (and any other delete action) used to fail with "Failed to execute \'json\' on \'Response\'" even though the record was removed. The delete now completes cleanly and the row disappears straight away.',
    'The Records pages load faster. The partnership and per-game stat tables were missing database indexes on the columns they join on, so a club with a long history took several seconds to load its records. Those indexes are now in place.',
  ],
}
