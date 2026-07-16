export default {
  version: 'v8.68.0.5',
  date: '2026-07-16',
  sortKey: '2026-07-16T15:00:00Z',
  title: 'Repair clubs already stuck with a dangling Stripe subscription id',
  items: [
    'The previous fix only stopped this happening to a club going forward. Any club already stuck with a leftover Stripe subscription id and nothing actually subscribed is now repaired automatically the next time the backend starts, so the "Redeem a discount code" box (and the normal new-signup checkout) comes back with no manual database work needed.',
  ],
}
