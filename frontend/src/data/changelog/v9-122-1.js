export default {
  version: 'v9.122.1',
  date: '2026-10-25',
  // Above v9.122.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T01:00:00Z',
  title: 'Vote settings list only the grades you are playing, and each team can choose who votes',
  items: [
    'In Vote settings, the grades a medal can count now list only the grades your club is playing this season. Teams from old seasons no longer clutter the list.',
    'If a medal still has an old grade ticked, it shows under the list as "Still ticked, but not played this season" with a button to remove it. It keeps counting until you do.',
    'There is a new "Who votes, by team" setting. For each team the medal counts, choose All players, Captain only, or the medal default. Seniors can count only the captain while the juniors let every player vote.',
    'The team setting applies on the public voting page, the player reminder, and the ballot form when you enter votes yourself. A team you have not set follows the "Who votes" default above it.',
  ],
}
