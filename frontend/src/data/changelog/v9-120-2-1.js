export default {
  version: 'v9.120.2.1',
  date: '2026-10-21',
  // Above v9.120.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-21T06:00:00Z',
  title: 'Vote reminders now show for players at big clubs',
  items: [
    'Vote reminders on the player\'s page were missing for some players. A club has a game open for every grade each round, and only the first ten open games were being checked, so a player\'s own game could be missed. It now looks up the games the player was actually in and checks those.',
    'A club that had already saved its own list of page modules did not get Votes, because it was not on that list. Votes is now switched on for those clubs. It is the same Votes tick in Availability, Self-service link, Player page, and a club that saves its list and leaves Votes off keeps it off.',
  ],
}
