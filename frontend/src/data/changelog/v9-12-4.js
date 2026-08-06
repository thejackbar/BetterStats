export default {
  version: 'v9.12.4',
  date: '2026-08-06',
  sortKey: '2026-08-11T14:00:00Z',
  title: 'Opposition players no longer count as ours',
  items: [
    'A match between two clubs that both sync BetterCricket is a single game in our records, carrying both sides’ batting, bowling and fielding. Fifteen queries were reading those games without checking which club a player actually belongs to, so the opposition were being counted as ours.',
    'The fielding leaderboard was affected with the Finals or Captain filter on. An opposition fielder could appear on your club’s board.',
    'BetterIQ Team analysis was affected throughout: fielding, bowling attack, bowling discipline, captaincy records, batting pairs, winning combinations, collapse analysis, batting by position and the batting breakdown. The average team score shown under each captain was including the opposition’s runs.',
    'Match review picked the best partnership of the game without checking whose it was, so it could report the opposition’s stand as yours.',
    'The teammates list could show players you had never played alongside, only against.',
    'An opponent scouting dossier could pick up players from a third club the opponent had played.',
    'Nothing about your stored data changed and no re-sync is needed. Every figure corrects itself the next time the page loads.',
  ],
}
