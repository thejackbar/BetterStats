export default {
  version: 'v8.8.0',
  date: '2026-06-09',
  sortKey: '2026-06-09T10:00:00Z',
  title: 'BetterSelect: redesigned Selection landing (matchday board)',
  items: [
    'The Selection screen is now a dense “matchday board”: one compact row per team, grouped by match day with sticky day headers. Built to scan a full weekend of 15+ teams at a glance instead of a wall of cards.',
    'Each row shows an at-a-glance health read: picked count (n/11), the worst issue flag, and a colour-coded status (Not started / In progress / Needs attention / Ready) down the left edge.',
    'Search by team or opponent, and filter by status (All / Needs attention / In progress / Ready) with live counts, plus a header tally of how many teams need attention vs are ready.',
    'Click a row to jump straight into the builder; tap the chevron to “peek”: it expands inline to the team balance (BAT/ALL/BWL/WK), captain & keeper, any warnings, the availability breakdown, and the full XI.',
    'Warnings match the builder exactly (short of XI, keeper out, no keeper/captain named, light on bowling) because the board now reads each player’s role and that day’s availability, so the landing page and the team builder always agree.',
  ],
}
