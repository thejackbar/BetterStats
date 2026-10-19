export default {
  version: 'v9.123.2.5',
  date: '2026-10-19',
  // Above v9.123.2.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T14:00:00Z',
  title: 'Sync links a team sheet entry by name the way it did before v9.123.2.4',
  items: [
    'Undid the change in v9.123.2.4 that stopped sync linking a team sheet entry to a player by name when that player already had a Cricket Australia id. We could not find a club where it had gone wrong, and it stopped the name link helping players whose id changes with a new registration.',
    'The hidden-player fix from v9.123.2.3 stays. Cricket Australia\'s shared placeholder id is still never linked to anyone.',
  ],
}
