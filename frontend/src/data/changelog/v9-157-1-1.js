export default {
  version: 'v9.157.1.1',
  date: '2026-11-27',
  // Above v9.157.1's sortKey (2026-11-27T21:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-27T22:00:00Z',
  title: 'Trial Summary: Trial ends soonest now orders ended trials by their end date',
  items: [
    'On Trial Summary, Trial ends soonest used to order only the trials still running. Ended trials stayed in sign-up order, so a trial that ended 3 days ago could sit below one that ended 27 days ago. Running trials now come first by end date, then ended trials with the most recently ended first, then clubs with no trial date.',
    'A new sort, Trial end date, latest first, puts the Trial ends column in one descending run. Least active first now puts the club with fewer page views first when two clubs have been active on the same number of days.',
  ],
}
