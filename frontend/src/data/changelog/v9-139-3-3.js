export default {
  version: 'v9.139.3.3',
  date: '2026-11-04',
  // Above v9.139.3.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T22:00:00Z',
  title: 'Player page: sections fill a two-across grid',
  items: [
    'Fixed: a player page with only a few sections left gaps, such as Player Cards alone on a row. The sections now fill a two-across grid in order, so four sections make a 2x2.',
    'A club with fewer sections, or a player who has none of one, gets the rest moved up to fill the space. Each section is still the same size, and a phone still shows one column.',
  ],
}
