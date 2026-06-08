export default {
  version: 'v8.5.0',
  date: '2026-06-08',
  sortKey: '2026-06-08T16:00:00Z',
  title: 'Caught behind & wicketkeeper catches split out',
  items: [
    'Caught behind is now its own dismissal, site-wide. Your batting “How I get out” breakdown separates being caught behind by the keeper from a regular catch — and so do the bowling “How I take wickets” breakdown, the Yearbook, BetterIQ Player Trends, Team Analysis, and the live opposition dossier.',
    'Wicketkeeper catches are now split from outfield catches everywhere they were still combined: BetterIQ Player Trends, the player snapshot card, the manual-entry review tables, and StatLab (new “WK catches” and outfield-catches stats you can sort and build leaderboards on).',
    'Behind the scenes: the keeper signal was always in the scorecards but was being thrown away on import — it’s now captured on every sync, with a one-command backfill to light it up across every club’s historical games.',
  ],
}
