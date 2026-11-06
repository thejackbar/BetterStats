export default {
  version: 'v9.139.5',
  date: '2026-11-04',
  // Above v9.139.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-16T00:00:00Z',
  title: 'Availability: clearer filters, full names, squads in order',
  items: [
    'Fixed: player names in the Availability grid were cut short (for example "Aamir Ab..."). The Player column is now as wide as the longest name and the week columns share the rest.',
    'New: a Show control beside the search box with Active, Dormant and Inactive. It opens on Active. Tap Inactive or Dormant to add them, and tap again to take them out. This replaces the Current squad and All switch, which could not hide inactive players once they were showing.',
    'Changed: "Hasn\'t played" is now "Last game", with this season, 1 season ago, 2 seasons ago, 3 seasons ago, 4 or more seasons ago and never played. A season runs from 1 September.',
    'Changed: squads in the Filters panel are short tappable chips with the club name left off ("1st XI", "2nd XI") instead of a long list of tick boxes. Competition shows once. The Leave out row above the grid is the only place to leave a competition out, and the panel no longer lists it a second time.',
    'Changed: the Filters panel heading "Show only" is now "Options".',
    'Fixed: squads, teams and grades with a number in the name now sort as numbers everywhere, so 1st XI comes before 2nd XI and both come before 10th XI. Before, 10th XI sat between 1st and 2nd.',
  ],
}
