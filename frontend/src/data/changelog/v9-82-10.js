export default {
  version: 'v9.82.10',
  date: '2026-09-19',
  // Above v9.82.9's sortKey. Check origin/main at merge time.
  sortKey: '2026-09-28T23:30:00Z',
  title: 'Club Diary dates enter properly again',
  items: [
    'On a Club Diary task the Start date, Due date and Estimated completion fields could not be typed in — the year kept resetting to a partial value (e.g. "0022") before you could finish it.',
    'Each field was saving to the server on every keystroke, and a native date box treats each digit of the year as a change. The finished save landed back on the box mid-typing and wiped the year. The dates now save when you leave the field, the same way the budget and third-party fields already do, so the whole date can be entered.',
  ],
}
