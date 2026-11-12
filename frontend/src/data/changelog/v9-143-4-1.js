export default {
  version: 'v9.143.4.1',
  date: '2026-11-12',
  // Above v9.143.4's sortKey (2026-11-19T22:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T23:00:00Z',
  title: 'Meta Ads HQ funnel says whose number each step is',
  items: [
    "Each step of the trial funnel now says where its number comes from: Meta for impressions, link clicks and landing page views, our own count for club selected and signups.",
    "The Club selected note now compares like with like: how many distinct visitors we saw pick a club, against how many Lead events Meta counted (events, not people, so the same person picking twice counts twice).",
    "The club list says it counts named clubs while the funnel counts visitors, and reconciles the two: clubs picked, visitor picks on them, and picks that could not be named.",
    "The stray self_serve_trial label is gone from the Free trial card. It was an internal tag; it stays in the tooltip.",
  ],
}
