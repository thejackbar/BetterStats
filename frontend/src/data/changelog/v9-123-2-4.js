export default {
  version: 'v9.123.2.4',
  date: '2026-10-19',
  // Above v9.123.2.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T13:00:00Z',
  title: 'Sync only links a team sheet entry by name to a player with no Cricket Australia id',
  items: [
    'Sync used to link a team sheet entry to your player by name when Cricket Australia gave that entry an id the club had not stored. It now does that only for a player added by hand who has no Cricket Australia id yet. A player who already has an id is never linked by name, so a different person with the same name cannot inherit their games.',
    'If someone re-registers under a new Cricket Australia id, merge the two records on the Merge Players screen and their games follow.',
    'This is a precaution. We looked for a club where it had already gone wrong and did not find one.',
  ],
}
