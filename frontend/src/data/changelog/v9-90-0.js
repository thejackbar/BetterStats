export default {
  version: 'v9.90.0',
  date: '2026-09-30',
  sortKey: '2026-09-30T02:00:00Z',
  title: 'Pay by invoice',
  items: [
    'A club can now choose to be invoiced for its subscription instead of paying by card. This is off for every club by default: clubs subscribe by card through Stripe unless a BetterCricket Super Admin switches invoicing on for them in All Clubs.',
    'Once it is on, any club admin can switch the club to Pay by invoice on the Account page, pick the modules and send the invoice. It is always emailed to the club\'s Primary Admin, whoever asked for it.',
    'The invoice is priced exactly like the card checkout, with the bundle discount and any discount code. GST is added on the invoice.',
    'The email has a link to pay the invoice through Stripe, by card or any other payment method offered there, and a link to the PDF. Invoices still to pay are also listed on the Account page with a Pay now button.',
    'Modules are subscribed once the invoice is paid. If the club is in a trial, its year starts when the trial ends, so paying early costs none of the trial.',
    'While the club stays on invoice billing, a renewal invoice for every current module is emailed 14 days before each year ends. It must be paid before the year ends. If it is not, the modules are paused until it is paid.',
    'Modules added part way through a year are invoiced for the rest of that year, so the whole club renews on one date.',
    'Super Admins can do all of this for a club from its Invoice button in All Clubs: switch invoicing on, raise and email an invoice, send the renewal invoice early, resend one or void one.',
  ],
}
