export default {
  version: 'v9.113.5',
  date: '2026-10-15',
  sortKey: '2026-10-15T09:00:00Z',
  title: 'History book figures: headline, Juniors and Masters picks, Team tab',
  items: [
    'A player whose figures include a career-level adjustment, such as a history book import, now reads the full combined Matches figure in the headline. It used to stay at the scorecard count because the Team tab failed for that player, so the headline had nothing to be raised to.',
    'That adjustment no longer shows under Juniors, Women\'s or Masters. It has no grade, so it was counted under every pick. It still shows under the club default, Men\'s and All.',
    'The Team tab no longer fails for a player with a career-level adjustment. Those matches are reported as recorded without a grade.',
    'Adding a history book that stops at a season now warns when a player already has an earlier whole-career import, because the two are counted separately and can overlap. The warning names the players and says where to undo the earlier import.',
    'The Matches note now calls the career total what it is: Cricket Australia\'s season figures plus any history the club has added.',
  ],
}
