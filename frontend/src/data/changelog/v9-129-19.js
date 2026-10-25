export default {
  version: 'v9.129.19',
  date: '2026-10-25',
  // Above v9.129.18's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T06:00:00Z',
  title: 'Fees: connecting Xero works again',
  items: [
    'Fixed: connecting Xero from Integrations ended on a Xero page saying "Invalid scope" (error code 500). Xero no longer lets newer apps ask for its old bank transactions permission, so BetterFees now asks for the newer read-only bank transactions and settings permissions instead. Clubs that connected earlier are unaffected.',
  ],
}
