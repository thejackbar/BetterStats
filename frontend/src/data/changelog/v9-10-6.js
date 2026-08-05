export default {
  version: 'v9.10.6',
  date: '2026-08-05',
  sortKey: '2026-08-09T23:00:00Z',
  title: 'Checkout works again when a discount code is applied',
  items: [
    'Proceeding to checkout with a discount code on top of the bundle discount failed instead of taking you to Stripe. Stripe allows a coupon only one discount slot, so the two are combined into one and labelled with both amounts, and that label was longer than the 40 characters Stripe accepts. It is now built to fit whatever the amounts and the code happen to be.',
    'The same limit was over-run by the plain bundle discount label as well, so a first subscription at a discount amount not used before could fail the same way.',
    'When something goes wrong the page now says what. Errors the server sends back with a real explanation were being replaced by "System refreshing. Please wait a moment…", which reads as the site being down when it is usually one specific thing that can be fixed. That message is now kept for what it was written for: the seconds during a deploy when the backend is genuinely unreachable.',
  ],
}
