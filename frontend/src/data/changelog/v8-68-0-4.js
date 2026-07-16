export default {
  version: 'v8.68.0.4',
  date: '2026-07-16',
  sortKey: '2026-07-16T14:00:00Z',
  title: 'Cancelling every module now actually cancels the Stripe subscription',
  items: [
    'Cancelling a club\'s last paid module (self-service or a super admin approving a cancel request) now cancels the underlying Stripe subscription and clears it from the club\'s record, instead of leaving a dangling subscription id behind. That dangling id was routing a club with nothing actually subscribed into the wrong checkout flow, one that has no discount-code support, blocking the "Redeem a discount code" box from ever working for it.',
  ],
}
