export default {
  version: 'v9.24.11',
  date: '2026-08-15',
  // sortKey only has to be greater than the current top entry, which is
  // v9.24.4 at 2026-08-17T20:00Z. The v9.24.5-10 entries carry 2026-08-15
  // sortKeys and so already sort below it — that ordering quirk predates this
  // entry and is left alone here.
  sortKey: '2026-08-17T21:00:00Z',
  title: 'The BetterAdmin module page now says what the module actually does',
  items: [
    'The public BetterAdmin page still described the module as fees, comms and merch. It now covers what it grew into: one member directory for the whole club, the volunteer roster and hours, committee meetings with minutes and motions, and the season club diary.',
    'Fixed two stale claims on the comparison page: merch was still listed as coming soon when it shipped a while back, and one row still priced the module as part of the retired Best tier.',
  ],
}
