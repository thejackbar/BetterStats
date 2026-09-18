export default {
  version: 'v9.82.2',
  date: '2026-09-18',
  // Above v9.82.1's sortKey (the highest on this branch). Check origin/main at
  // merge time.
  sortKey: '2026-09-28T18:00:00Z',
  title: 'A duplicate role now says where the role you cannot see lives',
  items: [
    'On BetterAdmin → Areas & roles → Roles, adding a role could be refused as already existing while no role of that name showed in the list. The committee starter pack seeds some roles (like "Bar Manager") as committee roles, which are managed on the Committee screen and never listed here — but the duplicate check still saw them.',
    'That refusal now says the clashing role exists as a committee role managed on the Committee screen, so you know where it is instead of hunting for a role that is not on the list. Give the new one a different name.',
  ],
}
