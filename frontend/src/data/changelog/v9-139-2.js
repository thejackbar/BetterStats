export default {
  version: 'v9.139.2',
  date: '2026-11-02',
  // Above v9.139.1.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T13:00:00Z',
  title: 'StatLab loads its reports much faster, and has team records like biggest chases',
  items: [
    'StatLab reports that list players (top run scorers, season and grade tables, anything with a filter on) now load in a second or two instead of ten to twenty-five on a big club. The figures are the same; we checked eleven reports against the old version row for row.',
    'New team records in the Match group: Biggest successful chases, Biggest chases against us, Lowest totals we defended, Lowest totals defended against us, Highest totals in a loss, Lowest totals in a win, and the highest- and lowest-scoring matches with both sides added together.',
    'A chase is the last innings of a match that the batting side won. The target is the other side\'s runs, less what the chasing side had already scored in earlier innings, plus one, so it works in two-day games as well as one-day ones.',
    'The Team innings table now names the team that batted, who they played, the grade, the date and our result. It used to show a blank NAME column.',
    'You can build your own chase reports too: Team innings has new Target, Successful chase, Total defended and Batting side won fields to filter and sort on.',
  ],
}
