export default {
  version: 'v9.132.7.1',
  date: '2026-10-28',
  // Above v9.132.7's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-09T23:30:00Z',
  title: 'Player page: availability answers save again',
  items: [
    'Fixed: tapping Available or Unavailable on a player\'s own page showed "That set could not be found." and the answer was not saved. The Player Cards sets update (v9.132.2) reused the name of the availability save, so every tap asked for a card set instead. Answers now save as before. Anyone who tapped in that time should answer again.',
  ],
}
