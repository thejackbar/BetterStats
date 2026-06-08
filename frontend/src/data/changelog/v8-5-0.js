export default {
  version: 'v8.5.0',
  date: '2026-06-08',
  sortKey: '2026-06-08T16:00:00Z',
  title: 'Caught behind & wicketkeeper catches split out',
  items: [
    'Caught behind is now its own dismissal. Your batting “How I get out” breakdown — and the same breakdowns in BetterIQ Player Trends and the Yearbook — now separate being caught behind by the keeper from a regular catch, instead of lumping every catch together.',
    'Wicketkeeper catches are now split from outfield catches everywhere they were still combined: BetterIQ Player Trends, the player snapshot card, the manual-entry review tables, and StatLab (new “WK catches” and outfield-catches stats you can sort and build leaderboards on).',
    'Behind the scenes: the keeper signal was always in the scorecards but was being thrown away on import — it’s now captured on every sync, with a backfill to light it up across historical games.',
  ],
}
