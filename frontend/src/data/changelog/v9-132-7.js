export default {
  version: 'v9.132.7',
  date: '2026-10-27',
  // Above v9.132.6's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-09T23:00:00Z',
  title: 'BetterSelect: a team moved to another grade keeps its XI, draft and votes',
  items: [
    'Fixed: when the association moves a team to another grade (Applecross 8th XI from One Day Grade 6 to Grade 5), Sync fixtures now moves the team\'s games across instead of cancelling them and starting empty Grade 5 ones. The game keeps its team, picked XI, draft, notes and votes. Games are paired by day and by your team\'s name, and only when there is exactly one on each side. Two games on one day are never guessed.',
    'Fixed: a game an earlier sync had already marked CANCELLED because the new grade was not known yet follows its team across the next time you press Sync fixtures, and the empty copy is removed.',
    'Fixed: a vote medal that counted the old grade now counts the new grade too, so votes cast before and after the move add up. Moving a squad\'s team to another grade on the Squads screen does the same. Only a medal limited to chosen grades is changed, and only by adding a grade. The Sync fixtures message names any medal it widened.',
    'Fixed: "Fill from last week" finds the team\'s last picked XI across the move, matching on your team\'s name when the grade changed.',
    'Games already played stay in the grade they were played in, so their stats are not moved.',
  ],
}
