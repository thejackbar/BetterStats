export default {
  version: 'v9.139.9.3',
  date: '2026-11-06',
  // Above v9.139.9.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-16T06:30:00Z',
  title: 'Club season pictures now load from the public site',
  items: [
    'The drawn season pictures (the card, feed and story images used in emails, share previews and ads) returned a "404 Not Found" from the public site even when they had been drawn. The site served every address ending in .png from its own files before it passed the request to the backend. The picture address now goes to the backend.',
  ],
}
