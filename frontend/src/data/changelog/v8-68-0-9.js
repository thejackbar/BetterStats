export default {
  version: 'v8.68.0.9',
  date: '2026-07-16',
  sortKey: '2026-07-16T19:00:00Z',
  title: 'Fix discount stacking order on the subscribe quote',
  items: [
    'A discount code that stacks with the bundle discount now applies to the amount left after the bundle discount, not the full pre-bundle price. Matching how Stripe actually charges it at checkout. The on-screen preview total now matches the real charge.',
  ],
}
