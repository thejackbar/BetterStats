export default {
  version: 'v9.106.5',
  date: '2026-10-04',
  sortKey: '2026-10-04T02:00:00Z',
  title: 'A player removed at their own request is gone from the whole public site',
  items: [
    'Removing a player used to take down their profile page but not their name everywhere else. Match scorecards, teammate lists, StatLab and the yearbook stat pages could still name them. Now every public page and data feed leaves them out: their name (in the forms a scorecard writes it) shows as "********" and their link goes nowhere.',
    'Your own signed-in admin screens (Directory, selection, fees and the rest) still show the real record, because the club needs it to run the club.',
    'Relatives are protected. If another player at the club shares the surname (a Tom or Sam Steenholdt beside a removed Trent), a line like "c T Steenholdt b Smith" or "c Steenholdt b Smith" is only masked when it can only mean the removed player. On a scorecard that is worked out from who actually played in that match, and when it could be either, it is left alone so the other player\'s record is never hidden by mistake.',
    'It only recognises names it has on record. A nickname nobody recorded is not caught, so check a removed player\'s old match pages once.',
  ],
}
