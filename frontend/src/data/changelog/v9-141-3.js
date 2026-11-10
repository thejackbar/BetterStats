export default {
  version: 'v9.141.3',
  date: '2026-11-09',
  // Above v9.141.2's sortKey (2026-11-19T02:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T03:00:00Z',
  title: 'Sync fixtures now brings in rounds already played, so Round 1 can be voted on',
  items: [
    'BetterSelect Sync fixtures used to keep only games still to come. A club that connected after Round 1 had been played never got Round 1 on the Fixtures page, and the voting screens read played games from that same list, so those rounds could not be voted on. Sync fixtures now also adds every game Cricket Australia has finished this season, marked Completed.',
    'A game you had already synced while it was upcoming keeps its picked XI, notes and votes, and now shows as Completed once it has been played. Games between two other clubs in your grade are still left out, and the public Fixtures page and BetterPosts still show only the games ahead.',
    'The result line after a sync now says how many already-played games were added. Press Sync fixtures once to pick up the earlier rounds.',
  ],
}
