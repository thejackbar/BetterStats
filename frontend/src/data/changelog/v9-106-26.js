export default {
  version: 'v9.106.26',
  date: '2026-10-05',
  sortKey: '2026-10-05T18:00:00Z',
  title: 'A player who bowled or batted now gets a match day in Accounts even if their appearance was not recorded',
  items: [
    'Accounts only counted a player as having played if the game held an appearance row for them. A player with a bowling spell, an innings or a catch but no appearance row was on the list with no match day for that game. Any of those now counts as playing, which is how the match counts elsewhere already work.',
    'Press Rebuild match days on Accounts once after this update and the missing days will come in.',
  ],
}
