export default {
  version: 'v8.78.1',
  date: '2026-07-23',
  sortKey: '2026-07-23T10:00:00Z',
  title: 'Match scorecard: fixed a stale cached score that could get stuck indefinitely',
  items: [
    'The live match data behind a scorecard was being cached with no expiry at all. If it happened to be fetched while a scorer was midway through correcting that match, an incomplete snapshot (an innings total with no batting rows behind it) could get stuck in place for as long as the server kept running. That live data is now cached for 15 minutes at most, and an incomplete-looking snapshot is never cached in the first place, so a page like this recovers on its own within a request or two instead of needing a restart.',
  ],
}
