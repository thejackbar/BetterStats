export default {
  version: 'v9.30.0.4',
  date: '2026-08-19',
  sortKey: '2026-08-27T09:00:00Z',
  title: 'Checkout: discount codes work again after the switch to live payments',
  items: [
    'A discount code entered at checkout failed with "No such coupon". Every code set up while the payment keys were still in test mode had been recorded against a test-mode coupon, which the live keys cannot see. A code now re-registers itself the first time it is used, so codes already handed out keep working and nothing has to be set up again.',
    'The same applied to the bundle discount and to the module records behind an add-on purchase. Both are now kept separately per payment mode, so a test-mode leftover can never be sent to the live payment system.',
    'A club whose payment customer record was created in test mode now gets a fresh one at checkout instead of the whole checkout being refused.',
  ],
}
