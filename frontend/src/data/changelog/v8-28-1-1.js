export default {
  version: 'v8.28.1.1',
  date: '2026-06-25',
  sortKey: '2026-06-25T14:00:00Z',
  title: 'Deleting a partnership record no longer throws a JSON error',
  items: [
    'Deleting a partnership record (and any other delete action) used to fail with "Failed to execute \'json\' on \'Response\'" even though the record was removed. The delete now completes cleanly and the row disappears straight away.',
  ],
}
