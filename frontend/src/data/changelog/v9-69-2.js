export default {
  version: 'v9.69.2',
  date: '2026-09-14',
  // Above main's v9.69.1 (2026-09-14T13:00:00Z), or SITE_VERSION
  // never reaches this release — the folder's highest sortKey is
  // what it reads.
  sortKey: '2026-09-14T14:00:00Z',
  title: 'Seasons swap over as they come across, not at the end',
  items: [
    'A CricketStatz import that replaces seasons you also sync used to leave every finished season counted from both sources until the whole run ended, so a record board watched mid-import showed doubles for the best part of an hour.',
    'Each season now changes over the moment its own matches are in, so a board is right while the import is still going.',
    'The screen says how many of the shared seasons have moved across so far.',
  ],
}
