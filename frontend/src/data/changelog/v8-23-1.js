export default {
  version: 'v8.23.1',
  date: '2026-06-20',
  sortKey: '2026-06-20T03:00:00Z',
  title: 'Scorecard upload reads boundaries, overs and partnerships',
  items: [
    'The scorecard reader now counts each batter\'s 4s and 6s from their scoring strokes, and works out a bowler\'s overs from how many over-columns are filled, including a part over from the last column.',
    'It also reads the fall-of-wickets table, including the STAND column, so an uploaded card keeps its partnerships. Both show on the match page like a synced game.',
    'A few more checks flag likely misreads before you import, like a batter whose 4s and 6s add up to more than their total, or bowlers whose overs do not add up to the innings.',
  ],
}
