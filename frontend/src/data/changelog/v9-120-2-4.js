export default {
  version: 'v9.120.2.4',
  date: '2026-10-22',
  // Above v9.120.2.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-22T09:00:00Z',
  title: 'Honour boards can list one award, and caps read Cap 186',
  items: [
    'An honour board that fills itself from a category now has an optional Only awards named box. Type A Grade Cap Number and the board lists just those awards, not every Club Award. Leave it blank and the board works as it did. The box suggests the award names already in that category.',
    'A cap shows as Cap 186 on honour boards, the Club Room TV and the public Honours page, and a board made only of numbered caps is in cap order. This only applies to awards named like a cap (A Grade Cap Number, 1st XI Cap, Club Cap), so a Captain or a Best Batter keeps its detail as typed.',
    'On a player\'s page, an award named like a cap and carrying a number now reads A Grade Cap 186 instead of leaving the number off.',
    'For separate men\'s and ladies\' cap boards, give each list its own award name, for example A Grade Cap Number and Women\'s A Grade Cap Number, and make one board for each.',
    'The awards import template has a cap number example row (Milestone, Cap Number, A Grade Cap Number, the number in Detail).',
  ],
}
