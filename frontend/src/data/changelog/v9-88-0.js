export default {
  version: 'v9.88.0',
  date: '2026-09-22',
  // Above v9.87.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-09-29T02:15:00Z',
  title: 'Roster: add shifts where you are, and a Coverage view you can drive by day',
  items: [
    'Adding a shift is now done where it belongs rather than from a button in the corner. On the People view every day\'s open-shifts cell has its own "+ Add a shift" (the day is filled in for you), and a collapsed area on the Areas view carries one too. Whichever way you add a shift, you can hand it to a volunteer in the same step.',
    'The "To fill" tab is now "Coverage". It has a Full week button and a button per day (pick more than one at once — say Tuesday and Thursday if that is when your nets run), so you can see exactly how many shifts are still open on the days you care about.',
    'For each open shift Coverage suggests the volunteer most likely to fill it, based on who is free that day, and assigns them in one tap — or pick someone else. You can also add a shift or a new volunteer straight from this view, so the whole job is on one screen.',
  ],
}
