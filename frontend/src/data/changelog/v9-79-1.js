export default {
  version: 'v9.79.1',
  date: '2026-09-10',
  // Above v9.79.0's sortKey, or SITE_VERSION never reaches this one. Check
  // origin/main at merge time.
  sortKey: '2026-09-25T18:00:00Z',
  title: 'The spreadsheet import shows which club it is writing to',
  items: [
    'The scorecard spreadsheet import now shows the club it will write to, in the review, before anything is imported. The club name comes from the server, so it is the club the import will actually land on, not whatever the page header happens to show.',
    'For a staff member who manages more than one club, the review asks you to confirm the club by hand before the import runs, and the Import button names it. This stops a whole history being written to the wrong club when the club you are managing is not the one you thought.',
    'If the club you are managing changes between setting up the import and running it, the import is refused rather than written to the wrong club, and the message tells you what happened.',
    'The result screen now says which club the matches were imported into.',
  ],
}
