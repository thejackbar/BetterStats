export default {
  version: 'v9.143.4',
  date: '2026-11-12',
  // Above v9.143.3's sortKey (2026-11-19T21:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T22:00:00Z',
  title: 'Player Cards: the Market, and filters by Wanted and role',
  items: [
    'There is a Market in Player Cards. It lists your cards that other players want, and who wants them, then every player with a visible wish list. The players whose list lines up with your cards come first, with how many of your cards they want and how many of theirs you want.',
    'Open a player to see their wish list beside yours. The cards you hold are outlined, and so are their cards that are on your list. Pick what to give and what to ask for and the swap builder opens with it filled in.',
    'Wish lists are now visible to the club by name. Anyone who would rather keep theirs private can switch it off in Settings under "Show my wish list in the Market". A private list still counts in the "wanted by" numbers and can still get a suggested swap with the one player it matches.',
    'My cards has a Wanted filter, which shows the cards other players are after. Doubles was already there. There is also a row of role filters (batters, bowlers, all-rounders, keepers) read from the role your club has recorded for each player. If the club has not recorded roles, the row does not show.',
    'Club cards can be filtered by role the same way. A held card that others want has a "See who wants it" link into the Market.',
    'Challenges can ask for roles. In the admin editor an exchange can be limited to some roles, and can ask for a minimum of a role, for example a squad of 11 with at least 1 keeper and 4 bowlers. A player with no role recorded does not count as any role.',
  ],
}
