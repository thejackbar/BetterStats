export default {
  version: 'v8.57.9',
  date: '2026-07-04',
  sortKey: '2026-07-04T22:00:00Z',
  title: 'BetterComms: load and add far more than 5000 contacts',
  items: [
    'The Contacts and Lists screens were capped at loading 5000 contacts, so a large directory (e.g. 9283) could only ever show or add the first 5000. The cap is now 50000, and adding a big selection to a list is done in a few queries instead of two per contact, so a whole filtered directory can go into a list at once.',
    'If a directory ever exceeds the cap, Contacts now says so and points you to narrow the search.',
  ],
}
