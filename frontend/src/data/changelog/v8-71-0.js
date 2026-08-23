export default {
  version: 'v8.71.0',
  date: '2026-07-17',
  sortKey: '2026-07-17T07:00:00Z',
  title: 'Billing: payment method management, discount reporting, clearer invoices',
  items: [
    "Added a note to the add-on purchase screen confirming the payment goes on the card already on file for the club's account.",
    'Removed the email receipt sent after an add-on purchase. Billing History on the Account page already covers it, so the confirmation message no longer promises a follow-up email.',
    'Billing History rows now show the modules paid for and the payment method used, alongside any bundle or coupon discount applied.',
    "Bundle discounts and coupon codes are now recorded separately in BetterCricket's own billing records, even where Stripe's own invoice can only show one combined discount line.",
    'New Super Admin "Discount Report" page: bundle discount totals by club, and coupon discount totals by club and by code, with date-range filtering.',
    "Primary Club Admins can now add, remove and set a default payment method from the Account page. Super Admins have the same controls for any club via a new Billing button in All Clubs. A payment method can only be removed when more than one is on file.",
  ],
}
