export default {
  version: 'v9.68.2.1',
  date: '2026-09-07',
  // Must sort above v9.67.4's 2026-09-13T18:00:00Z key, which is the highest in
  // the folder — the 9.68.x releases carry earlier keys, so a real 2026-09-07
  // timestamp would sort this below them and SITE_VERSION would stay on v9.67.4.
  sortKey: '2026-09-13T19:00:00Z',
  title: 'The BetterCricket version number is off your public pages',
  items: [
    'A club’s own public pages no longer carry the BetterCricket build number beside the club name — a visitor reading your stats has no use for it.',
    'It still shows in the admin app, where it is what you quote when reporting something.',
  ],
}
