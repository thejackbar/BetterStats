export default {
  version: 'v9.113.0',
  date: '2026-10-15',
  sortKey: '2026-10-15T14:00:00Z',
  title: 'Winter and summer seasons stay separate, and totals no longer lag a scorecard',
  items: [
    'Winter 2026 and Summer 2026/27 are now two seasons everywhere. Both start in 2026, and the app used to treat the year as the season, so the season filter showed 2026/27 twice and a player\'s summer line included their winter games. They are now separate in the season filter, the season tables, season totals and the innings list. Where a club has both in a year, the summer one is labelled Summer 2026/27.',
    'A new switch on Admin > Seasons, "Count winter and summer as one season per year", puts a club back to one season per year, with winter and summer added together. It is off by default. Clubs that only play one season a year see no change.',
    'A player\'s totals no longer sit behind a scorecard we already hold. Cricket Australia\'s season totals can run a few days behind a finished game, so a profile could show the match but not the runs. Where the scorecards we hold add up to more than the season total, the profile header and the season table now use the scorecards, and a line under Matches says what was added. Cricket Australia\'s figure is never lowered, and a season it has no row for yet now gets one once a game is held.',
    'Sync now checks a game again for two weeks after it is played. A game with one innings missing from its first pull used to stay that way. Sync fills in missing batting, bowling and fielding rows from the scorecard it has already fetched. It only adds rows and never changes or removes one.',
    'Recent form on the admin player profile now shows the last five batting innings (a star marks not out), the last five bowling spells, and the season\'s fielding: catches, wicketkeeper catches, run outs and stumpings. A did-not-bat row no longer shows as a 0. "This season" is now the season of the club\'s latest game, so it no longer lands on winter once summer has started.',
  ],
}
