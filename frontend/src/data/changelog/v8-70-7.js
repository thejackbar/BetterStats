export default {
  version: 'v8.70.7',
  date: '2026-07-17',
  sortKey: '2026-07-17T04:00:00Z',
  title: 'Fix invoice.paid webhook silently no-op\'ing (no receipt email, no billing history)',
  items: [
    'Found live: our Stripe account\'s API version nests an invoice\'s subscription under a different field than this app was reading, so every invoice.paid and invoice.payment_failed webhook was silently doing nothing ("unknown subscription"), no receipt email, and the payment never showed up in Billing History. Module access itself was never affected, since that\'s granted at the moment of payment, not by the webhook. Fixed to read both the old and new field shapes.',
  ],
}
