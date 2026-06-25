export default {
  version: 'v8.28.1.1',
  date: '2026-06-25',
  sortKey: '2026-06-25T14:00:00Z',
  title: 'Drop impossible partnership records',
  items: [
    'Fixed a few phantom partnership stands that came from a bad fall-of-wickets figure in the source data, like a "381" stand between two batters who only made 25 and 1 between them. A stand is now checked against what the two batters actually scored, so an impossible total is thrown out instead of shown as a record. The existing rows have been cleaned up and a re-sync will not bring them back.',
  ],
}
