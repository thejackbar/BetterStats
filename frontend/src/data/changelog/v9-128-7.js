export default {
  version: 'v9.128.7',
  date: '2026-10-21',
  // Above v9.128.6.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T00:00:00Z',
  title: 'Availability: filter by gender and competition, and leave one out in a tap',
  items: [
    'Availability has a Gender filter (Men, Women, Not set). "Not set" finds the players whose gender nobody has recorded, so they are never quietly dropped when you pick Men or Women. It shows once anyone on the list has a gender recorded.',
    'Availability has a Competition filter built from the competitions your club has games in from here on. A competition with no game coming up is not offered. A player counts as being in a competition when their squad plays in a grade that is grouped into it.',
    'A "Leave out" row under the filters hides a competition in one tap, for example the Veterans. It only hides players whose one competition is the one you left out. Someone who also plays in another competition stays on the list, and so does anyone whose squad is not grouped into a competition yet. The row shows once there are two or more competitions.',
  ],
}
