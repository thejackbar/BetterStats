export default {
  version: 'v9.129.32.1',
  date: '2026-10-26',
  // Above v9.129.32's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T23:00:00Z',
  title: 'A player who pulled out of a game no longer counts it as a match played',
  items: [
    'Fixed: a player named for a game who then withdrew before it was played was still counted as having played it. Cricket Australia took them off the final team sheet, but our copy of the sheet was read earlier and never corrected, so their Matches figure sat one above Cricket Australia\'s and play.cricket\'s. A game from the last two weeks is now checked against the final team sheet on every sync, and a player who is no longer on it comes off the count.',
    'A player who is still on the final sheet under a different Cricket Australia id is left alone, and so is anyone with a batting, bowling or fielding line in the game. The change is recorded in the audit log, so it can be undone, and a player who is put back on the sheet counts again.',
  ],
}
