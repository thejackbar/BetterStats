export default {
  version: 'v9.129.28.1',
  date: '2026-10-26',
  // Above v9.129.28's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T17:00:00Z',
  title: 'Two teams in one grade can have their own voters',
  items: [
    'Fixed: when two of a club\'s teams play the same grade (two teams in One Day Grade 6, say), a team\'s voting setting was shared by both. People chosen to vote for one team were the only ones who could vote for the other.',
    'In Votes, Settings, under "Who votes, by team", each team in a shared grade now has its own row, with its own mode and its own chosen people. A grade only one of your teams plays looks the same as before.',
    'A setting made before this fix is shown on both teams, as it was already applying to both. Change each team\'s row to what it should be. Nothing else needs doing.',
  ],
}
