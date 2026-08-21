export default {
  version: 'v9.42.2',
  date: '2026-08-21',
  sortKey: '2026-08-21T21:00:00Z',
  title: 'Nets: every player is findable at check-in, and turning up is not the same as batting',
  items: [
    'Fixed: a player who reads as active on your Players screen could be missing from net check-in entirely. The list left out anyone who had not played a game recently and said nothing about it, so the only way to record them was as a guest under their own name. Check-in now reaches every player at the club. Your current squad is still what you see first, and searching finds the rest.',
    'Someone can now turn up and not bat. They count as having been there, they stay off the batting queue so the rotation never lands on an empty net, and you can leave a note about why.',
    'Up next is only what is still to come. Batted and Not batting are their own lists underneath, so a long queue is a real one.',
    'The row buttons are cricket bats now rather than a lightning bolt: a green arrow for bat next, a tick for marking someone as batted, and a no-entry mark for taking them out of the rotation. A key above the list says what each does, and you can hide it once you know them.',
    'The attendance download for a session says who was not batting, any note against them, and whether they checked themselves in or you did.',
  ],
}
