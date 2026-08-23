export default {
  version: 'v8.70.3',
  date: '2026-07-16',
  sortKey: '2026-07-17T00:00:00Z',
  title: 'Fix checkout tax error and resolve a club\'s real address at signup',
  items: [
    'Subscribing was failing at checkout with "Automatic tax calculation in Checkout requires a valid address on the Customer". A side effect of a recent fix that has BetterCricket create the Stripe customer itself instead of leaving it to Stripe. Checkout now saves the billing address entered at checkout onto that customer, so tax always calculates correctly.',
    'Self-serve club registration now also resolves the club\'s real address (PlayHQ\'s public directory first, falling back to the already-crawled Club Directory) and stores it on the club, so the Stripe customer created at checkout has a real address from the very first attempt.',
  ],
}
