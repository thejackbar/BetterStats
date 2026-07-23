export default {
  version: 'v8.78.2',
  date: '2026-07-23',
  sortKey: '2026-07-23T11:00:00Z',
  title: 'Match scorecard: fixed a crash that silently dropped the whole rebuild',
  items: [
    'The rebuilt scorecard (see the last two entries) could silently fail and fall all the way back to an old, incomplete copy on a game whose grade or season record can\'t be traced back to a club in our system, a state that can genuinely happen and was already handled everywhere else on this page. One missed check meant that state crashed the rebuild instead, and the crash was swallowed rather than shown, so the page just looked wrong with no clue why.',
    'Fixed, and made sturdier at the same time: figuring out which side of a match is "us" no longer leans on that club lookup at all when it can be avoided. It now checks first whether we already hold stored stats for anyone in either team\'s lineup on this exact game, which settles the question directly, and only falls back to matching the club\'s name against the lineup when that check has nothing to go on.',
  ],
}
