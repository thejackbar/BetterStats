export default {
  version: 'v9.50.1',
  date: '2026-08-23',
  sortKey: '2026-08-23T19:00:00Z',
  title: 'Commission is earned on a confirmed Stripe payment, not a deal’s stage',
  items: [
    'A rep now earns commission when money actually arrives. A deal’s stage is a judgement someone can drag around; a paid Stripe invoice is a fact, and it is the only thing that creates an entitlement to be paid.',
    'Only new business earns: a club’s first payment, and later payments that add modules. An annual renewal of what the club already holds earns nothing. That is the club not cancelling, not a sale. Stripe’s own billing reason is what tells them apart.',
    'Figures are net of GST. Tax collected on our behalf was never revenue and is not commissioned.',
    'The rep and the rate are stamped onto each payment when it lands, so changing a rate later can never rewrite what a past payment earned.',
    'The earned table now reads Payments and Paid by clubs, and opens the actual payments behind the figure: what was bought, when it was paid, at what rate.',
    'python -m app.scripts.backfill_invoice_commission stamps invoices recorded before this shipped (dry run by default).',
  ],
}
