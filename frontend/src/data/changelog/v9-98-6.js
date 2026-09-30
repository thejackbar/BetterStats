export default {
  version: 'v9.98.6',
  date: '2026-10-05',
  // Above v9.98.5's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-05T14:00:00Z',
  title: 'Entered scorecards put each side’s score under the right team',
  items: [
    'On a scorecard you entered by hand or imported from a spreadsheet, the header could show your score under the opposition’s name and theirs under yours. It happened when the opposition batted first, and also when both teams’ names ended in the same age group, such as two “Over 60s” sides. Each score now sits under the team that made it.',
    'Your innings is now labelled with the team name the match was played under, such as “Portland Over 60s”, rather than the club’s own name. The same name heads your bowling figures.',
    'The match spreadsheet has a new bowling_order column. Number your bowlers 1, 2, 3 in the order they came on and the scorecard lists them that way. A sheet without the column keeps its own row order.',
    'Choosing “All seasons” on the Games page now stays chosen, instead of jumping back to the newest season.',
  ],
}
