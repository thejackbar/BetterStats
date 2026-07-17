export default {
  version: 'v8.71.1',
  date: '2026-07-17',
  sortKey: '2026-07-17T08:00:00Z',
  title: 'Fixed a Super Admin trial status not actually saving',
  items: [
    'Fixed a bug in the All Clubs module editor: choosing "Trial" from a module\'s status dropdown only opened a start/end date editor without saving it, unlike every other status, which applied straight away. A Super Admin could pick Trial, move on, and the module would silently stay Active. The club still showed as Subscribed on its own Account page, with no way to tick the module for the real checkout flow.',
    'Choosing Trial now applies immediately with sensible default dates (now, plus the default trial length), which can still be adjusted afterwards.',
    "Fixed the All Clubs module editor and a club's own Account page sometimes disagreeing on a BetterAdmin (fees/comms/merch) module's status when its three parts were out of sync, by making both read the same rule for which status to show.",
  ],
}
