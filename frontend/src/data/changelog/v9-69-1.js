export default {
  version: 'v9.69.1',
  date: '2026-09-07',
  // Only has to sort above the current top entry — see the note in v9-69-0.js.
  sortKey: '2026-09-14T18:00:00Z',
  title: 'Imported results are no longer counted twice',
  items: [
    'A CricketStatz import no longer brings across matches your club already has from Cricket Australia. It used to add a second copy of every overlapping fixture, so those innings counted twice on every board — the same score could appear twice in Highest Individual Scores, and career runs and matches read high.',
    'Averages hid it: doubling the runs and the dismissals together leaves the average unchanged, so only the counts moved.',
    'Seasons only CricketStatz has are unaffected and still come across in full.',
    'If your club already imported before this, Data Sync now has a "Results counted twice?" check that finds the duplicates and removes them, keeping your own copy of each. Anything you have edited by hand is left alone and listed for you.',
    'A finished import now says how many matches it left as Cricket Australia has them, so a figure that looks short reads as explained rather than missing.',
  ],
}
