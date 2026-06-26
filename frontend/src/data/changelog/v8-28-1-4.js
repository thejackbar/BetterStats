export default {
  version: 'v8.28.1.4',
  date: '2026-06-26',
  sortKey: '2026-06-26T11:00:00Z',
  title: 'Stop the notifications bell erroring out',
  items: [
    'The notifications bell now falls back to an empty panel instead of a server error if one of the things it reads is unavailable for a club, for example a club whose database is missing a recent update. The upcoming milestones and the rest of the panel still load. This is a stronger version of the resilience fix from the last release.',
  ],
}
