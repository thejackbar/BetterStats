export default {
  version: 'v9.123.3.1',
  date: '2026-10-19',
  // Above v9.123.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T15:00:00Z',
  title: 'Merge Duplicates stops two people who share a name being merged in bulk',
  items: [
    'A pair of records with the same name can be two people, like a junior and an adult with the same name. If both records have a game on the same date in different games, they cannot be one person. Merge Duplicates now marks that pair "Probably two people" and leaves it out of Bulk Approve.',
    'Merging that pair by hand still works. The screen asks first, shows how many dates clash, and only merges if you say yes.',
    'The same check applies to the merge_player_pair script, which now needs --allow-shared-games to go ahead.',
  ],
}
