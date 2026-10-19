export default {
  version: 'v9.123.2.4',
  date: '2026-10-19',
  // Above v9.123.2.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T13:00:00Z',
  title: 'A player with the same name no longer inherits someone else\'s games',
  items: [
    'Fixed sync linking a team sheet entry to your player by name when Cricket Australia had given that entry a different id. A junior with the same name as an adult could have their games put on the adult\'s record. One player read 16 junior games they did not play.',
    'Sync now links by name only to a player added by hand who has no Cricket Australia id yet, which is what the name link was for. A player who already has an id is never linked by name. If someone re-registers under a new id, merge the two records on the Merge Players screen and their games follow.',
    'Games that were already attached to the wrong player stay until they are cleaned up. If a player\'s games or career look too high, send us the name and we will check each game against the scorecard and remove the ones that are not theirs. Every change is logged and can be undone.',
  ],
}
