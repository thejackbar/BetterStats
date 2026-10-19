export default {
  version: 'v9.110.14',
  date: '2026-10-13',
  sortKey: '2026-10-13T16:00:00Z',
  title: 'Syncing fixtures now removes games that are no longer on the draw',
  items: [
    'Syncing fixtures only ever added games. If Cricket Australia redrew a round or called a game off, the old entry stayed on the list beside the new one, so you saw duplicates and games that were not happening.',
    'Sync now compares your list with the current draw. A game that came back under a new listing is updated in place, so its team, XI and votes stay with it. A game that is gone is removed.',
    'If you had already picked an XI or collected votes on a game that has gone, it is kept and marked Cancelled, and left off availability and selection, so nothing you entered is lost. Delete it when you are ready.',
    'Press Sync twice and you now get the draw as it stands at that moment, not what was fetched up to half an hour earlier.',
    'If Cricket Australia does not answer for a grade, that grade\'s fixtures are left alone.',
  ],
}
