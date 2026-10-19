export default {
  version: 'v9.123.2',
  date: '2026-10-19',
  // Above v9.123.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T09:00:00Z',
  title: 'Results posts pull the whole weekend, and unwanted rows can be removed',
  items: [
    'Pull latest round on a Results post now brings in Saturday and Sunday together. Before, it loaded one day and the other sat behind the match-day dropdown, so a club that plays across both days had to paste a Sunday link to get everything. Fixtures already worked this way.',
    'The Fixtures and Results rows no longer run off the edge of a narrow editor panel. The grade, scores and margin boxes shrink to fit, so you can see the whole row and the ✕ button on the right that removes it. Use that to drop a team you do not want on the post, such as a vets side.',
  ],
}
