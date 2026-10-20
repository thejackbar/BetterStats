export default {
  version: 'v9.123.6.1',
  date: '2026-10-19',
  // Above v9.123.6's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-28T10:00:00Z',
  title: 'Records page loads again for clubs with a long history',
  items: [
    'The records page for a club with decades of scorebook history could sit on "Loading records" for a minute or two and then say "No records data available". The two partnership boards (best partnership per wicket, and best per grade) were looking up each grade\'s display name once for every partnership. They now do it once per grade, so the same page loads in a couple of seconds.',
    'Nothing on the page changes. The names, rankings and rows are the same as before, checked on a copy of a large club with the old and new code side by side.',
  ],
}
