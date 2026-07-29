export default {
  version: 'v8.94.2',
  date: '2026-07-30',
  sortKey: '2026-07-30T06:00:00Z',
  title: 'Player renames no longer break Play.Cricket / scorecard matching',
  items: [
    'A renamed player (a preferred name, a married name) now keeps matching correctly on the Lineups page and the live match scorecard, even though a Play.Cricket team list still uses their old name.',
    'Renaming a player anywhere in BetterCricket now automatically remembers their old name, so this keeps working on its own for every future rename — no extra step needed.',
    'New "Also known as" section on a player\'s profile (Edit) lets you add or remove a former name by hand — the fix for a rename that happened before today, or any other name a feed happens to use for them.',
  ],
}
