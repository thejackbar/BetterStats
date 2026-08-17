export default {
  version: 'v9.25.0',
  date: '2026-08-16',
  sortKey: '2026-08-19T01:00:00Z',
  title: 'The automatic sync runs on Perth time, pulls only the period\'s results, and skips a period with no fixtures',
  items: [
    'The scheduled sync now runs Sunday and Monday at 1am Perth time. It used to fire at 3am UTC, which is 11am Sunday in WA, so a club\'s weekend results landed most of a day after they were played.',
    'Each run pulls only the fixtures played since that club\'s last successful sync, instead of re-reading the club\'s entire history every week. Sunday covers the weekend, Monday covers anything a scorer entered during Sunday.',
    'If a run fails to pull match results, the next one covers that period again rather than starting from where the failed run stopped. A club whose Sunday sync failed asks for a fortnight of fixtures, not a week, and the sync history says so instead of showing a green tick.',
    'If nothing was played in the period, nothing is pulled. Each run checks the club\'s fixtures for the period first, so the off-season, the Christmas break and a bye weekend all cost nothing and pick straight back up the week a game is played.',
    'Archived clubs, switched-off clubs and clubs whose subscription has lapsed are no longer synced.',
    'A club with no synced history yet, or one that has fallen a long way behind, still gets a full pull. That decision is made per club, not by the calendar.',
    'New on Data Sync: a notice when Cricket Australia has revised a past season since BetterStats last read it, naming the seasons and showing what moved. A monthly check looks for this, since the ordinary sync no longer revisits older seasons.',
  ],
}
