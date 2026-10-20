export default {
  version: 'v9.102.13',
  date: '2026-10-02',
  sortKey: '2026-10-02T23:30:00Z',
  title: 'Leaderboard grade toggles and StatLab now count the same matches',
  items: [
    'Picking A Grade, B Grade and so on on the Club Leaderboard now shows matches played, the same number the all grades view, a player\'s profile and StatLab show. The grade views were counting only the matches a player batted in on the batting board, bowled in on the bowling board and fielded in on the fielding board, so a player picked for a game and not used could read 6 where StatLab read 11.',
    'Picking a grade on the Club Leaderboard while Finals only or Captain only is switched on no longer fails to load. It now shows that grade\'s finals or captain figures.',
    'StatLab\'s Grade filter now finds a grade your club has renamed. Picking "Premier" for a grade you renamed from "1st Grade" used to list nobody. The old name still works in saved reports.',
  ],
}
