export default {
  version: 'v9.111.2',
  date: '2026-10-14',
  sortKey: '2026-10-14T15:00:00Z',
  title: 'Games the other club loaded first now show the right winner',
  items: [
    'Fixed: a game against a club that loaded it first could show your win as a loss, because the winner was never written down and the page fell back to the other club\'s verdict. The sync now records the winning team on every game it revisits, so each club sees the result from its own side. Run Sync Now once to correct games already loaded.',
  ],
}
