export default {
  version: 'v8.76.1',
  date: '2026-07-21',
  sortKey: '2026-07-21T13:00:00Z',
  title: 'Fixed uploaded scorecards missing from the club Games page',
  items: [
    'A scorecard uploaded through the admin scorecard upload tool without a Grade picked (Grade is optional there) never showed up on the club\'s public Games page. The page always filters by season, and that filter was only reaching the season through the Grade, so a game with no grade had no season to match against. Season is now read directly off the uploaded game, so it shows up straight away.',
    'While fixing that, closed a gap where one club\'s manually uploaded games could be pulled into another club\'s Games list and win/loss record.',
  ],
}
