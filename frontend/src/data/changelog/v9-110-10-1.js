export default {
  version: 'v9.110.10.1',
  date: '2026-10-15',
  sortKey: '2026-10-15T09:00:00Z',
  title: 'Team tab fix, and a warning when two imports cover one player',
  items: [
    'A player whose figures include a career-level adjustment, such as an import that stops at a season, got an error on the Team tab of their profile. It now loads, and those matches are reported as recorded without a grade.',
    'Adding a history book that stops at a season now warns when a player already has an earlier whole-career import, because the two are counted separately and can overlap. The warning names the players and says where to undo the earlier import.',
  ],
}
