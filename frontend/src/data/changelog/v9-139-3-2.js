export default {
  version: 'v9.139.3.2',
  date: '2026-11-03',
  // Above v9.139.3.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T21:00:00Z',
  title: 'Player page: sections now sit in matching pairs',
  items: [
    'Fixed: the sections on your player page were uneven. Availability sat alone at half width above a full-width Player Cards bar, and the rest flowed in around them. Every section is now the same size.',
    'The sections are paired in the order you use them: Availability next to Selection, Player Cards next to Fantasy, Stats next to Voting, then Club admin. On a phone they stack in that same order.',
    'Opening one section no longer stretches the one beside it. A club without a section keeps the rest of its pairs as they are.',
  ],
}
