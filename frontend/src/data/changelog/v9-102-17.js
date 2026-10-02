export default {
  version: 'v9.102.17',
  date: '2026-10-03',
  sortKey: '2026-10-03T03:00:00Z',
  title: 'Typed player names follow your name format setting',
  items: [
    'A player whose name was typed in as "Damian O\'Hara" now shows as "O\'Hara, Damian" like everyone else, and sits in surname order in the Availability grid, Selection and the other player lists.',
    'BetterSelect now respects the Player name format in Admin, Settings. If your club shows First name Surname, the Availability grid, Selection, Squads, Players and the BetterSelect home page all show it that way. Search and sorting still go by surname.',
    'Only a plain two word name is flipped. A one word nickname, or a name with three or more words, stays exactly as you typed it, because we cannot tell a middle name from a double barrelled surname. Nothing stored is changed, so you can still edit the name in Admin, Players.',
  ],
}
