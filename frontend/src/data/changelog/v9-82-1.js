export default {
  version: 'v9.82.1',
  date: '2026-09-18',
  // Above v9.82.0's sortKey (the current highest on this line), or SITE_VERSION
  // never reaches this one. Check origin/main at merge time.
  sortKey: '2026-09-28T07:00:00Z',
  title: 'Expand an operational area into its roles on the roster',
  items: [
    'In BetterAdmin → Roster → Areas, an operational area that involves several roles now expands into a row per role. A Match Day area opens up into Umpires, Scorers and Team Managers, each with its own shifts down the week, so you can see and fill each role on its own rather than reading them all pooled in one row.',
    'A single-role area is unchanged — there is nothing to open into, so it stays as one row.',
    'Areas start collapsed and remember which ones you have opened, so a club with many areas keeps a compact overview and only expands the ones it is working on.',
  ],
}
