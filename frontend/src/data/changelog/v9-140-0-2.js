export default {
  version: 'v9.140.0.2',
  date: '2026-11-06',
  // Above v9.140.0.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-16T11:00:00Z',
  title: 'Club season pages use a primary and a secondary colour',
  items: [
    'The season page now takes two colours from the club\'s logo, as a paid club\'s site does. The main colour is the accent. The second colour is the biggest other colour in the logo, and it shows in the bar beside the header and the menu underline. A one-colour logo uses that colour for both.',
    'Colours made before this are read again the next time backfill_club_teaser_themes runs. It only fetches each logo again, with no search and no Cricket Australia data call.',
  ],
}
