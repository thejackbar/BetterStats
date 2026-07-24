export default {
  version: 'v8.80.3',
  date: '2026-07-24',
  sortKey: '2026-07-24T20:00:00Z',
  title: 'Uploaded scorecards: flag where the old card itself doesn\'t add up',
  items: [
    'The reader transcribes an old scorecard exactly as written. Where the card\'s own figures don\'t reconcile (batting that doesn\'t match the stated total, wickets that don\'t tally), the review screen now says so plainly and treats it as a probable original scorer\'s error, not a reader mistake, so you can correct it or import the card as-is to keep it faithful.',
    'These "the card doesn\'t add up" flags are kept separate from likely misreads (a bowler name that isn\'t in the bowling figures), which are the ones actually worth fixing before importing.',
    'The import confirmation spells out the choice: keep the card\'s original numbers, or go back and edit.',
  ],
}
