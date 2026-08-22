export default {
  version: 'v9.47.0',
  date: '2026-08-22',
  sortKey: '2026-08-22T14:00:00Z',
  title: 'A theme belongs to one plan',
  items: [
    'Reported, and it was serious: a second strategic plan drew the first plan’s themes, an objective added to the second read as belonging to both, and deleting a theme from the second plan’s tree deleted the first plan’s objectives.',
    'A theme now belongs to one plan, and the objectives under it belong to that plan. There is no linkage between one plan’s hierarchy and another’s. A plan draws its own themes and nothing else.',
    'Deleting a theme can only ever reach its own plan’s objectives. Deleting a plan takes its themes with it. Actions and motions are still never deleted by any of this — they are kept and stop being linked.',
    'Existing plans are converted on upgrade. A theme used by two plans is split so each plan keeps its own copy with its own objectives; a theme with no objectives at all cannot be attributed, so it is listed under “Not on a plan” at the foot of the tree, where it can be moved or deleted.',
    'When you write an objective, the theme list offers only the chosen plan’s themes, and changing the plan clears the theme.',
  ],
}
