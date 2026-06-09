export default {
  version: 'v2.13.3 Beta',
  date: '2026-06-03',
  sortKey: '2026-06-04T09:00:00Z',
  title: 'BetterIQ — Club MVP now counts every player',
  items: [
    'Found why high-value batters (e.g. Monument, Seen) were missing from Club MVPs: the rating gated and divided by a “matches” figure that the data feed sometimes leaves at 0 even when runs and innings are recorded — so those players were dropped before they were ever scored. It now uses a robust games count (the greatest of matches, batting innings and bowling innings), so everyone with real output is included and rated. With the quality-weighted blend, in-form batters now surface.',
  ],
}
