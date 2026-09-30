export default {
  version: 'v9.100.1',
  date: '2026-09-30',
  sortKey: '2026-10-07T12:00:00Z',
  title: 'Clubs with a very long history no longer stall the season lookup',
  items: [
    'A club with 100 or more seasons on Cricket Australia (one had 119) could send the season lookup round in circles, because the feed hands back the whole history in one go and ignores paging. It now reads the list once and stops as soon as a page brings nothing new.',
  ],
}
