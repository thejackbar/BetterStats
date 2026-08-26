export default {
  version: 'v9.53.5.1',
  date: '2026-08-25',
  sortKey: '2026-08-25T22:00:00Z',
  title: 'Importing a scorecard into BetterPosts works again',
  items: [
    'Pasting a match link on the Scorecard post reported “Scorecard parse error: greenlet_spawn has not been called” and pulled nothing through. The lookup behind it named a column that does not exist, and the tidy-up after that failure is what produced the message on screen. Both are fixed, and a pasted link now fills in both teams’ batting, bowling, totals and match details as it should.',
    'A player whose record has been merged into another now shows under the name the club actually kept, rather than falling back to whatever the feed spelled.',
  ],
}
