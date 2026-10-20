export default {
  version: 'v9.106.15',
  date: '2026-10-05',
  sortKey: '2026-10-05T21:00:00Z',
  title: 'Fantasy: the player trace now sees imported and paired matches',
  items: [
    'The Fantasy player trace used to look only at synced scorecard rows. A player whose games were typed in or imported from CricketStatz showed no games at all, which made a played game look missing.',
    'It now reads the same effective views the scoring uses, so imported and hand-typed games show up, tagged api or manual, with the match, grade, round and the first reason a game would not count.',
    'A synced game that is hidden because an imported copy of the same match is preferred now says so, and names the imported match, instead of disappearing from the list.',
  ],
}
