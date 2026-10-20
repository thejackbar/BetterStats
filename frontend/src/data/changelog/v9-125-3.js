export default {
  version: 'v9.125.3',
  date: '2026-10-20',
  // Above v9.125.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-04T11:00:00Z',
  title: 'Card review: suggestions as you type, a season dropdown, and fixes to the doubles list',
  items: [
    'The opposition, player and grade boxes on every Card review page now suggest names from your club as you type. A misspelling still finds the name, so "richie" offers Ritchie, and the list is headed Closest matches when it is guessing. Pick with the mouse or with the arrow keys and Enter. The player search also forgives a misspelt name that is typed in full, and the page says which player it used.',
    'There is a season dropdown in the filters on every step, and Find a match keeps it.',
    'Fixed: searching for a player on Possible doubles could spin forever, or ask the server over and over. It now loads once. A search with no answer says so, and says when no player at the club matches the name.',
    'Fixed: the doubles list offered two different matches as a strong double. Two cards from different weeks that happened to share two low scores were listed together even though the opposition and the result differed. When both cards have batters, a strong match now needs most of the smaller card to appear on the other with the same scores. A weaker match is offered only for the same day and the same opposition, and is marked Likely. The list will be shorter than before.',
    'Fixed: player searches were slow on a large club. They now look the player up first, about ten times faster on a club with thousands of matches.',
    'Fixed: switching to Marked as different briefly showed the open pairs with Put back buttons until the new list arrived.',
  ],
}
