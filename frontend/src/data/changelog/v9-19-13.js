export default {
  version: 'v9.19.13',
  date: '2026-08-12',
  sortKey: '2026-08-16T04:00:00Z',
  title: 'BetterFees season rollover: undo, find-and-add, and remove',
  items: [
    'Rolled players over before the new season\'s fee schedule was ready? "Remove all" on the Accounts page clears every member out of that season in one go, so you can set up the rate card and roll over again. Anyone with a payment already recorded is kept, never deleted.',
    'The Rollover screen now warns up front if the destination season has no fee schedule yet, since a rollover with nothing to match tiers against lands everyone as "needs tier".',
    '"Add member" can now find anyone the club already knows, including a player who sat out last season or one new to the club, and add them straight into this season\'s fee list, instead of only being able to create a brand-new non-playing person.',
    'Each member row (and the bulk-select bar) now has a Remove action, for a player you know isn\'t coming back. It only clears their line in this season: their record and every other season are untouched, and it\'s refused if a payment is already recorded against them this season.',
  ],
}
