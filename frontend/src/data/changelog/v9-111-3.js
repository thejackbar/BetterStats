export default {
  version: 'v9.111.3',
  date: '2026-10-14',
  sortKey: '2026-10-14T16:00:00Z',
  title: 'Club ID on Data Sync no longer looks like a fault',
  items: [
    'The Club ID line on Data Sync is the club\'s PlayHQ id, which the sync does not use. It said game-level data needs it, which was wrong and made a club with it unset look broken. The line now says syncing results does not need it.',
    'Looking the id up by the first word of the club name rarely found the right club. It now tries the full name first.',
  ],
}
