export default {
  version: 'v9.128.6',
  date: '2026-10-21',
  // Above v9.128.5.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-05T20:00:00Z',
  title: 'Match fees default to EFT, and Square is a payment method',
  items: [
    'Recording a match-fee payment on a person\'s Accounts page now starts on EFT. It used to copy their membership payment method, so someone who paid their membership by PlayHQ or cash had their match fees pre-set the same way. Switching the Kind to Match Day on the payment form also puts EFT back.',
    'A match-fee payment saved with no method is stored as EFT.',
    'Square is now in the payment method list when you log a payment, record a bulk payment or import payments from a bank statement.',
  ],
}
