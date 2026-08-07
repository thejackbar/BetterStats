export default {
  version: 'v9.18.0',
  date: '2026-08-06',
  sortKey: '2026-08-14T11:00:00Z',
  title: 'Junior grades split out of career stats',
  items: [
    'Runs and wickets from junior grades no longer sit inside a senior career average. An Under-14 season now counts separately, so a player who made 200 against other 14-year-olds and 50 in first grade reads as a first-grade batsman.',
    'The split is a filter, not a deletion. Every stats page has an Include row where Juniors can be switched back on for the page you are looking at, and switching it on brings the junior figures straight back.',
    'Women\'s, Masters and Mixed grades each get the same toggle, and all three count by default. Only junior is left out to begin with. A club that runs none of these never sees a toggle it has no use for.',
    'Picking a specific grade from a Grade dropdown always shows that grade. Choosing Under 14s gives you the Under 14s, whatever the Include row says.',
    'Clubs can set their own default from Settings, under Stats by grade. A club whose cricket is mostly junior can have juniors counted from the outset rather than asking every visitor to switch them on.',
    'A grade counts as junior based on how it is classified on the Grades screen. Anything not yet classified is guessed from its name, so Under 14s, Colts and Year 7 are caught without anyone labelling them first.',
    'Applies across career totals on a player profile, the season-by-season table underneath it, the Leaderboard, and club Records.',
    'Historical figures imported from a spreadsheet still count. An import filed against a senior grade stays in the totals when juniors are switched off, and the older records a club holds as totals rather than scorecards are kept as well.',
    'A player who has only ever played junior cricket opens their own profile on their junior figures, not a page of zeroes, and the page says why. Switching Juniors off by hand still does exactly that — the fallback only decides what loads first. It can be turned off from Settings.',
    'Nothing changes for a club with no junior grades. Their pages run exactly the queries they ran before.',
  ],
}
