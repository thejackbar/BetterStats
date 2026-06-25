export default {
  version: 'v8.26.1.1',
  date: '2026-06-25',
  sortKey: '2026-06-25T10:00:00Z',
  title: 'Fix: the post designer crashing on the Mosaic lineup template',
  items: [
    'The BetterSocials post designer threw "Something went wrong" on open when the Mosaic lineup template was the last one used. With no players picked yet, the empty featured slot was read as a player and crashed the page. The Mosaic grid now renders empty until you add players, like the other templates.',
  ],
}
