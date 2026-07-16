export default {
  version: 'v8.66.11',
  date: '2026-07-15',
  sortKey: '2026-07-15T23:00:00Z',
  title: 'Fixed add-on module pricing wrongly including the bundle discount',
  items: [
    "Adding a module to an already-live subscription was still picking up the initial bundle discount if it hadn't yet been used on a regular invoice — the price preview and the actual charge both now correctly bill at the full prorated rate with no discount.",
    'The price preview for an add-on module now breaks down each module\'s full annual price, the prorata deduction, and the amount charged today.',
  ],
}
