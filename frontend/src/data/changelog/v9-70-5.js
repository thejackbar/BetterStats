export default {
  version: 'v9.70.5',
  date: '2026-09-16',
  // Above v9.70.4, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-16T14:00:00Z',
  title: 'The duplicate check ran once, then silently gave up',
  items: [
    'Reported by two clubs: the check that pairs an imported match with the one your sync already holds worked the first time and then wrote nothing at all on every run after it, so both sources were still being counted.',
    'It was refusing its own work — moving a match from one record to another briefly left two records pointing at one game, and the whole pass was thrown away rather than saved. It clears and re-files in one step now.',
    'Where several of your sides played the same club on the same day and nothing tells the fixtures apart, the pairing now settles the same way every time instead of being reshuffled each night.',
  ],
}
