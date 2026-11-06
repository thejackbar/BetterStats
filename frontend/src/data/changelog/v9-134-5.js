export default {
  version: 'v9.134.5',
  date: '2026-10-29',
  // Above v9.134.3's sortKey (v9.134.4 is on its own branch). Check origin/main at merge time.
  sortKey: '2026-11-11T14:30:00Z',
  title: 'A game abandoned after play started now counts as a match',
  items: [
    'If a game was abandoned after the first ball was bowled, every player named in the side now gets the match, even if they did not bat, bowl or field. Cricket Australia counts it that way. Before, a named player with no line of their own lost the game from their total.',
    'A game abandoned with no play at all (a washout) still does not count, and a cancelled game never counts. A fixture Cricket Australia marks completed but with both teams abandoned is also unchanged.',
    'Because the same rule decides who is charged a match day, a player named in an abandoned game that did start will now show a match fee for it. The club can waive it.',
  ],
}
