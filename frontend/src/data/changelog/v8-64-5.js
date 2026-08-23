export default {
  version: 'v8.64.5',
  date: '2026-07-15',
  sortKey: '2026-07-15T10:00:00Z',
  title: 'Fixed BetterSocials missing its subscribed/trial status on the Dashboard',
  items: [
    'BetterSocials now shows its Subscribed/Trial status and date on the Dashboard, matching BetterSelect and every other module: it was being looked up under the wrong internal key, since BetterSocials renders as a combined tile (Post Designer + Website) with a different key to its billing record.',
    'Fixed the same underlying mismatch for BetterSocials\' pending-request badge and its START TRIAL button, which would have silently failed for the same reason.',
  ],
}
