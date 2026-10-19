export default {
  version: 'v9.122.3',
  date: '2026-10-25',
  // Above v9.122.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T04:00:00Z',
  title: 'Ask IQ can judge a game that has been played, and Match Review shows the real score',
  items: [
    'Ask IQ can now look at games that are already finished. Ask for the 3-2-1 for the most recent 3rd XI game, or paste a match link, and it reads the scorecard and gives you three names with a reason for each.',
    'It weighs the context of the game, such as batting first or chasing, a collapse, or the best stand. It also looks at runs against the team total and the batting slot, and economy and maidens.',
    'Wickets are not just counted. Each one carries the slot and score of the batter it removed, so an opener or a set batter is worth more than a number 10. Three wickets that included both openers can beat four tail-end wickets.',
    'Ask IQ finds a game by the side you picked it as (3rd XI) or by the grade it was played in (5th Grade), so you do not need to know which one the club used.',
    'Match Review now shows the real team scores, extras included. It used to add up the batters\' runs only, so a chase could read 101/1 against 127/9 and still say Won. If a game has no stored totals the score is marked approximate and the summary leaves it out until a sync fills it in.',
  ],
}
