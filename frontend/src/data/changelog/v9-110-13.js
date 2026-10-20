export default {
  version: 'v9.110.13',
  date: '2026-10-13',
  sortKey: '2026-10-13T15:00:00Z',
  title: 'Profile Matches figure now agrees with the Analysis tab',
  items: [
    'A player profile could show one Matches figure in the header and a higher one on the Analysis tab. One player read 95 in the header and 96 under Analysis, and 96 was right.',
    'The header was Cricket Australia\'s own season total, which can miss a game we hold a scorecard for. The Analysis tab compares both sources for each season and grade and keeps the higher. The header now takes that same total whenever it is higher.',
    'The header only ever goes up. Where Cricket Australia counts more matches than we hold scorecards for, the header keeps its figure.',
    'This lifts the header for players whose scorecards outnumber the season totals. The "i" beside Matches still shows both sources.',
  ],
}
