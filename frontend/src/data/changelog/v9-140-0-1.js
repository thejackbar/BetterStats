export default {
  version: 'v9.140.0.1',
  date: '2026-11-06',
  // Above v9.140.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-16T10:00:00Z',
  title: 'Club season pages now find the club crest',
  items: [
    'The club directory held no crest address for any club, so the new season page had no crest and no club colours to show. The crawl\'s own club search already returns the crest, so a pulled club now keeps it at no extra call, and the page falls back to the directory\'s crest for clubs pulled earlier.',
    'backfill_club_teaser_themes now also looks up the crest for clubs that have none (one paced club search each), stores it on the directory row only where that is empty, then reads the colours from it.',
  ],
}
