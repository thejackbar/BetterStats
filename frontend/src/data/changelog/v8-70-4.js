export default {
  version: 'v8.70.4',
  date: '2026-07-17',
  sortKey: '2026-07-17T01:00:00Z',
  title: 'Recover from "no payment method" when adding modules',
  items: [
    'Adding modules to an already-subscribed club used to dead-end with a raw Stripe error if the club had no payment method on file to charge. It now sends the club to a Stripe-hosted page to add a card, then automatically finishes the same purchase once they\'re back, no more starting over.',
  ],
}
