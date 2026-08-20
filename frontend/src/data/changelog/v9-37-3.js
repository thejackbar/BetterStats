export default {
  version: 'v9.37.3',
  date: '2026-08-20',
  sortKey: '2026-09-04T18:00:00Z',
  title: 'A player profile shows what they played, season by season and grade by grade',
  items: [
    'Analysis → Team on a player profile has a second table under the by-grade one: seasons down the side, a column for each grade the player has turned out in, and the number of games in each. A dash means they did not play in that grade that season, which is a different thing from playing and not being counted.',
    'The grade columns read in the order your club set on Manage Grades, so Seniors comes before Reserves comes before Under 19s rather than whichever grade happens to have the most games against it. A grade you have not placed sits after the ones you have. A grade that has been merged is one column under the name you kept, and a grade you have renamed reads under your name for it.',
    'Merge Grades is now called Manage Grades. The screen has done labels, public visibility, renames and ordering for a while, and merging is only one of the five.',
    'Fixed: a player whose career mixes seasons Cricket Australia has broken down by grade with seasons we only hold scorecards for was counting short. The two were being compared against each other across the whole career rather than season by season, so the scorecard seasons were swallowed by the aggregate ones. A player reading 10 matches against a real 15 now reads 15, and that flows through to the grade milestones on their profile.',
  ],
}
