export default {
  version: 'v9.25.0',
  date: '2026-08-16',
  sortKey: '2026-08-19T01:00:00Z',
  title: 'The automatic sync runs on Perth time, pulls only recent results, and leaves off-season clubs alone',
  items: [
    'The scheduled sync now runs Sunday and Monday at 3am Perth time. It used to fire at 3am UTC, which is 11am Sunday in WA, so a club\'s weekend results landed most of a day after they were played.',
    'Each run pulls only the fixtures played since that club\'s last successful sync, instead of re-reading the club\'s entire history every week. Sunday covers the weekend, Monday covers anything a scorer entered during Sunday.',
    'A club whose season has finished is left alone. The run checks whether anything was actually played in the period before pulling anything at all, so an off-season club costs nothing until its fixtures start again.',
    'Archived clubs, switched-off clubs and clubs whose subscription has lapsed are no longer synced.',
    'A club with no synced history yet, or one that has fallen a long way behind, still gets a full pull. That decision is made per club, not by the calendar.',
    'New on Data Sync: a notice when Cricket Australia has revised a past season since BetterStats last read it, naming the seasons and showing what moved. A monthly check looks for this, since the ordinary sync no longer revisits older seasons.',
  ],
}
