export default {
  version: 'v9.82.7',
  date: '2026-09-18',
  // Above v9.82.6's sortKey. Check origin/main at merge time.
  sortKey: '2026-09-28T22:00:00Z',
  title: 'The roster tells you when a week predates your latest areas & roles',
  items: [
    'A roster week is built once, from your operational-area patterns, the first time it is opened. Editing a pattern in Areas & roles afterwards only rebuilds a week that has no shifts yet, so a week already in progress quietly keeps the shifts it was born with. If you had restructured your areas, that week could still be showing the old ones (under "Archived areas" on the Areas view) with none of your new patterns, and nothing said why.',
    'On BetterAdmin → Roster, a draft week that holds shifts on areas you have since changed or archived now carries a banner saying so, with a "Reset the week" button that rebuilds it from your current patterns. Reset clears any assignments on that week, as it always has.',
  ],
}
