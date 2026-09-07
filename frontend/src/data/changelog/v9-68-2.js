export default {
  version: 'v9.68.2',
  date: '2026-09-07',
  sortKey: '2026-09-07T12:00:00Z',
  title: 'Nothing overwrites a scorecard you entered yourself',
  items: [
    'Re-running a CricketStatz import no longer writes over a match you have corrected by hand. It skips those and tells you which ones it left alone.',
    'A match nobody has touched is still refreshed, so a re-import remains the way to bring back anything a merge cost you.',
    'Standing rule now checked in the build: a function may add to your manual entries or move them, but it can only replace what it wrote itself.',
  ],
}
