export default {
  version: 'v9.135.2',
  date: '2026-10-29',
  // Above v9.135.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-12T15:00:00Z',
  title: 'Merge Duplicates: cards show a player\'s scorebook games',
  items: [
    'Fixed: on the Merge Duplicates cards a player who only exists in the club\'s scorebook (a CricketStatz import or a typed card) showed 0 seasons, 0 runs, 0 wickets and 0 innings, even where their profile holds 20 matches. The cards now count the same way the profile does, and add a Games figure and the years the player\'s games run across, for example "2019 to 2020". A record with no games at all still reads 0.',
  ],
}
