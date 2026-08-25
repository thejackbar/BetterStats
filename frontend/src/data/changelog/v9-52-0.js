export default {
  version: 'v9.52.0',
  date: '2026-08-23',
  sortKey: '2026-08-23T18:00:00Z',
  title: 'One kind of button across BetterAdmin, and Facilities loads again',
  items: [
    'Facilities would not open. It read "Could not load facilities." whatever the club held, because it was reading the wrong field off the asset list, and that took the whole screen down rather than just that one list. Fixed, and a list that cannot be read now costs that list instead of the page.',
    'Every screen in BetterAdmin now uses the same buttons the Committee screen does. Accounts, Payments, Stock, Club Diary, Events, Facilities and Reports were each drawing their own, so moving between them meant four different-looking controls for the same job.',
    'The Directory\'s Membership, Role, More and Manage buttons have moved up beside the heading, centred, with the search on its own line underneath. Payments\' Membership, Role and More did the same.',
    'The Roster\'s People / Areas / Confirm / Hours row, Facilities\' Availability / Requests / Assets, Events\' two buttons and Reports\' Money / Stock are all centred on the title line now, in that same control.',
    'Search boxes added to Club Diary, Events, Facilities and Areas & roles. Each one searches its whole section rather than the list on screen, so searching Facilities finds a booking by name and keeps the space it is on.',
  ],
}
