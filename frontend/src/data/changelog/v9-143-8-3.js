export default {
  version: 'v9.143.8.3',
  date: '2026-11-13',
  // Above v9.143.8.2's sortKey (2026-11-20T08:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T09:00:00Z',
  title: 'Fielding: the fix for missing bowlers and keepers now reaches older games',
  items: [
    "The catch and stumping fix from the last update only applied to scorecards that had never been read, so re-reading a club did nothing for matches already stored. The re-read can now be pointed at the matches whose stored catches and stumpings add up to more than the bowler list holds, or at every match.",
  ],
}
