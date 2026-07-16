export default {
  version: 'v8.68.1.0',
  date: '2026-07-16',
  sortKey: '2026-07-16T20:00:00Z',
  title: 'Fix checkout failure when a discount code stacks with the bundle discount',
  items: [
    'Subscribing with a stacking discount code alongside the bundle discount was failing at the last step ("Array discounts exceeded maximum 1 allowed elements") — Stripe only allows one discount on a checkout. The two discounts are now combined into a single one before checkout, so subscribing with a stacking code works end to end and charges the same total the preview showed.',
  ],
}
