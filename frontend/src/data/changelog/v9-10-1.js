export default {
  version: 'v9.10.1',
  date: '2026-08-05',
  sortKey: '2026-08-09T09:00:00Z',
  title: 'Creating a discount code says what went wrong',
  items: [
    'Fixed: creating a discount code could fail with a bare internal server error. Stripe was refusing the coupon and nothing caught it, so the reason never reached the screen. Whatever Stripe objects to now comes back as a sentence on the form.',
    'A display name longer than 40 characters no longer stops a code being created. The full name is kept in BetterCricket, and a club\'s invoice shows the first 40, which is all Stripe allows there.',
    'A percentage above 100 or at 0, or a dollar discount of 0, is now refused on the form instead of on the way to Stripe.',
    'A code that fails to save no longer leaves a coupon behind in Stripe with nothing pointing at it.',
  ],
}
