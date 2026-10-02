export default {
  version: 'v9.102.8',
  date: '2026-10-02',
  sortKey: '2026-10-02T09:00:00Z',
  title: 'A player removed at their own request is gone from the whole public site',
  items: [
    'Removing a player used to take down their profile page but not their name everywhere else. Match scorecards, teammate lists, StatLab and the yearbook stat pages could still name them. Now every public page and data feed leaves them out: their name (in the forms a scorecard writes it) shows as "Player removed" and their link goes nowhere.',
    'Your own signed-in admin screens (Directory, selection, fees and the rest) still show the real record, because the club needs it to run the club.',
    'It only recognises names it has on record. A nickname nobody recorded, or a surname another player shares, is not caught, so check a removed player\'s old match pages once.',
  ],
}
