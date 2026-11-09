export default {
  version: 'v9.141.2',
  date: '2026-11-09',
  // Above v9.141.1's sortKey (2026-11-19T01:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T02:00:00Z',
  title: 'Segments: pick only the clubs whose teaser pictures are all on file',
  items: [
    'BetterComms Segments (BetterCricket outreach) has a new rule, "Club has a full set of teaser pictures". Pick yes to reach only the contacts whose club has every picture on file, so the dashboard in an email always shows. Pick no for everyone else, including contacts with no club.',
    'The older choice "Snapshot and picture ready" only records that a club was drawn. It cannot see the files, so a club drawn before the dashboard picture existed counted as ready and got an empty box in the email. The new rule looks at the files themselves, and a club with no snapshot, a junior-only club or a failed pull never counts.',
    'A new read-only report, report_teaser_picture_coverage, says how many crawled clubs had nothing to build pictures from (and why), how many have a full set, a partial set or none, and how many email contacts the new rule reaches.',
  ],
}
