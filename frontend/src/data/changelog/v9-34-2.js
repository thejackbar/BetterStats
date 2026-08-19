export default {
  version: 'v9.34.2',
  date: '2026-08-19',
  sortKey: '2026-09-02T09:00:00Z',
  title: 'Sales: the Attributed filter was coming back empty',
  items: [
    'Picking a rep under Attributed showed no clubs at all. The filter was right, but the queue\'s own default was cancelling it out: with none of the Called, Callback or Voicemail boxes ticked, the queue only ever shows clubs that have never been called, and a club is only ever earned by a call or an email. So the two could almost never both be true. Picking someone under Attributed now leaves the call status alone, and ticking Called, Callback or Voicemail still narrows it.',
    'There is also a command that goes back over every call and email already on record and attributes each club to the rep who earned it, for anything the upgrade itself did not cover. It shows what it would do before it does anything, and it never moves a club that has already been attributed.',
  ],
}
