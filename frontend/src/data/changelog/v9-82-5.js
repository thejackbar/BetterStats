export default {
  version: 'v9.82.5',
  date: '2026-09-18',
  // Above v9.82.4's sortKey (the highest on origin/main). Check origin/main at
  // merge time.
  sortKey: '2026-09-28T21:00:00Z',
  title: 'Rostering onto a shift whose area was archived no longer fails',
  items: [
    'On BetterAdmin → Roster, allocating a volunteer to an open shift could be refused with "Unknown volunteer or area" — even a qualified volunteer to a shift in their own role. That happened when the shift belonged to an operational area that had since been archived. Since each shift now carries its own role and the qualification that gates it, the allocation never needed the area at all; the old check was insisting the area still be active. It has been removed, so a shift on an archived area can be filled like any other.',
    'The "Best fit for this shift" panel is also shown for such a shift now, naming its area from the shift itself, so there is a way to fill it from the panel rather than only by dragging.',
  ],
}
