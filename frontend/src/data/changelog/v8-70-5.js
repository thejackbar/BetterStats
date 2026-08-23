export default {
  version: 'v8.70.5',
  date: '2026-07-17',
  sortKey: '2026-07-17T02:00:00Z',
  title: 'Fix the missing-payment-method recovery page failing to load',
  items: [
    'The new "add a payment method" recovery page (shown when adding modules fails because a club has no card on file) was itself failing with a server error. A missing currency parameter on the page Stripe generates. Fixed.',
  ],
}
