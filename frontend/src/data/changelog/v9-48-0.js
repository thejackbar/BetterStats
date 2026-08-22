export default {
  version: 'v9.48.0',
  date: '2026-08-22',
  sortKey: '2026-08-22T16:30:00Z',
  title: 'A plan owns its themes, and a theme owns its objectives',
  items: [
    'There is no club-wide theme any more. A theme belongs to one plan, an objective belongs to its theme and takes that theme’s plan, and a plan’s themes and objectives are entirely separate from every other plan’s.',
    'The database enforces it rather than the screens being careful about it, so a theme with no plan, an objective with no plan, and an objective with no theme are all states that can no longer be reached.',
    'Deleting a plan takes its themes and their objectives. Deleting a theme takes its own plan’s objectives. Neither can reach another plan, and the confirm counts what goes before it happens.',
    'Actions and motions are still never deleted by any of this. They are kept and simply stop being linked to an objective, which is the one rule that does not move.',
    'Nothing a club wrote is deleted on upgrade. Anything that was not on a plan is carried into a plan named “Unfiled work”, and an objective with no theme is filed under a “General” theme inside its own plan, so it can be seen and moved onto a real plan. The only thing removed is a theme that had no plan and nothing under it.',
    'Writing an objective now asks for a plan and a theme before it will save, and the theme list offers only the chosen plan’s themes.',
    'Fixed while here: sending a plan or a theme belonging to another club came back as a server error rather than a plain refusal.',
  ],
}
