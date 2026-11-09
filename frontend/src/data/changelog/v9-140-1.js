export default {
  version: 'v9.140.1',
  date: '2026-11-09',
  // Above v9.140.0.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-18T01:00:00Z',
  title: 'Club crests are kept on our own server',
  items: [
    'Each club\'s crest is now saved once, as a small PNG on the same media volume as the season pictures, and the season page and the picture drawer load it from our server instead of from the host it came from. A crest that is missing from the volume falls back to the original address.',
    'backfill_club_teaser_themes now also keeps the crest, so one run covers the colours and the crest. Clubs that already have colours but no kept crest are picked up on the next run. New pulls keep it as part of the pull.',
    'Only a logo we can decode as a picture is kept, and it is re-saved as a plain PNG no bigger than 256 pixels a side, so nothing else is ever served from our domain.',
  ],
}
