export default {
  version: 'v8.77.2',
  date: '2026-07-22',
  sortKey: '2026-07-22T12:00:00Z',
  title: 'BetterImport now matches grades/teams to your online data',
  items: [
    'A club sheet with a Grade/Team column (e.g. "1A", "B", "A/R") used to be compared against online data under that exact grade name. A club\'s own shorthand almost never matches the real grade name we hold, so that portion silently read as "nothing online for this grade" and got added on top of a career that was already fully synced.',
    'The import wizard now has a "Match grades" step: pick the real online grade each label corresponds to (games, players and runs are shown so you can tell you\'ve got the right one), or confirm "no online equivalent" for a grade that genuinely predates online records. Anything left unmatched falls back to the safe whole-career comparison instead of assuming there\'s no overlap.',
    'If your club has uploaded a sheet with a Grade/Team column before, undo that import and re-run it so the fix applies. The reconciler only recomputes from what\'s stored, so an old import needs a fresh pass to pick up the corrected grade matching.',
  ],
}
