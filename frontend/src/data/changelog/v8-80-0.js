export default {
  version: 'v8.80.0',
  date: '2026-07-24',
  sortKey: '2026-07-24T12:00:00Z',
  title: 'Upload Scorecard reads more card formats, PDFs and old-era scorebooks',
  items: [
    'The scorecard reader now understands association match-summary forms (one page with your batting, your bowlers, an own-catches column and the opposition as a bare total), not just the two-page scorebook. Catches and stumpings from an own-catches column come through as a matchable fielding table on the review screen, with keeper catches kept separate.',
    'PDF scans upload directly, alongside photos. A multi-page PDF of one match reads the same as separate photos.',
    'Old cards read better: tally strokes in the extras boxes are no longer mistaken for numbers, "7/164" style scores are understood, two-digit years land in the right century, and pre-1980 cards are recognised as 8-ball-over cricket.',
    'When the result box is blank but the scores decide the match, the reader fills the result in and the review screen flags it as worked out, not written, so you can check it before importing.',
  ],
}
