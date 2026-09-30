export default {
  version: 'v9.99.2',
  date: '2026-09-30',
  sortKey: '2026-09-30T10:00:00Z',
  title: 'Manual games say what does not add up',
  items: [
    'Fixed a hand-entered game showing the opposition\'s total on our side as well. If you flipped an innings from "Opposition" to "Our innings", the total you had typed stayed on it out of sight and replaced our batters\' score. Flipping the side now clears it, and our innings is always totalled from its batters and extras.',
    'The Manual Games form now tells you when a game does not add up: no opposition total, bowlers who do not reach the opposition\'s score, a result line that disagrees with the totals, or an innings set to the wrong side. It only warns. You can always save, even when you do not have the figure.',
    'Games already saved with a copy of the other side\'s total can be repaired with `python -m app.scripts.fix_stray_innings_totals <club|all>` (a dry run unless you add --apply).',
  ],
}
