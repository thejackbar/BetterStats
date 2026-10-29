export default {
  version: 'v9.129.37',
  date: '2026-10-26',
  // Above v9.129.36's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-09T01:30:00Z',
  title: 'Merged players no longer show as FILL-IN on old scorecards',
  items: [
    'A player you had merged into another record could still show on a match scorecard as "S Johnson" with a FILL-IN badge, even though the merge was done. The scorecard now follows your merge history, so the row links to the player you kept and shows their name.',
    'If Cricket Australia gave that player a different id on the scorecard, the card also matches the short name ("S Johnson") against the old full name the merge remembered ("Shaylyn Johnson"). It only does this when exactly one player fits.',
  ],
}
