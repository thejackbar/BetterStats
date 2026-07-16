export default {
  version: 'v8.68.1.2',
  date: '2026-07-16',
  sortKey: '2026-07-16T22:00:00Z',
  title: 'Fix backend startup hang on a Stripe API call',
  items: [
    'The one-off repair for clubs with a leftover Stripe subscription link ran during backend startup and made a real call to Stripe for each one it found. The first time it had a real one to act on, it hung the whole backend at "Waiting for application startup" with no crash and no way to recover except a fresh deploy. It now runs in the background instead, so a slow or unreachable Stripe response can never hold up the backend coming online.',
  ],
}
