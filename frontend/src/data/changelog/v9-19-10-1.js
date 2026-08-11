export default {
  version: 'v9.19.10.1',
  date: '2026-08-11',
  // Must sort above v9.19.10's 2026-08-16T01:00:00Z key.
  sortKey: '2026-08-16T01:15:00Z',
  title: 'Fix: BetterPosts scorecard always showed 0 overs',
  items: [
    'The Scorecard post pulled from a match link always showed "0 OV" and a run rate of 0, whatever the real match. The innings total-overs field on the live match data is named differently than what was being read; it now pulls through correctly.',
  ],
}
