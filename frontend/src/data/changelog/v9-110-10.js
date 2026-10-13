export default {
  version: 'v9.110.10',
  date: '2026-10-13',
  sortKey: '2026-10-13T12:00:00Z',
  title: 'Import a club history book that stops at a season',
  items: [
    'Import historical stats now handles a history book that ends at a point in time, like a century book that finishes with 2004/05. On the Columns step choose "Only up to a season" and type the last season the book covers.',
    'The book is compared with each player\'s online record up to that season only. Where the two overlap, the online figures stay and the book adds just the part online is missing. Everything online after that season is kept and added on top, so a player whose online record starts in 2012 no longer has their book swallowed.',
    'The review shows the book, the online record to that season, what the book adds and the online record after it, side by side. A cut-off that is not two years (2004/05) is refused, and a sheet row dated after the cut-off is named before anything is saved.',
    'The upload step has a history book template with the headings a printed record book uses (Games Played, No Innings, Total Runs, NO, No 50\'s, No 100\'s, Highest Score, Overs Bowled, Total Wickets, Best Bowling Inn, Catches), and those headings now map on their own.',
    'Past imports show which ones stop at a season.',
  ],
}
