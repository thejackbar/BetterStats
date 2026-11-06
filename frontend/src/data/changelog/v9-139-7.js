export default {
  version: 'v9.139.7',
  date: '2026-11-05',
  // Above v9.139.6.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-16T03:30:00Z',
  title: 'Every paying club on the "Trusted by clubs at" strip',
  items: [
    'New: the "Trusted by clubs at" strip on the home page and /trial now adds every club that is paying for BetterStats, newest first, after the clubs already on it. A club that signs up appears without anyone editing the page.',
    'A club is listed only when it is live, public (not behind an access PIN) and on a paid BetterStats subscription, and has a crest uploaded. Clubs on a trial, a lapsed or cancelled club, a club in a payment grace period and an archived club are left out.',
    'A Super Admin who wants a paying club kept off the strip sets TRUSTED_CLUBS_EXCLUDE on the server (a comma-separated list of club slugs).',
    'Changed: the strip scrolls at the same pace however many clubs are on it, and a crest that fails to load shows the club\'s initials instead of a broken picture.',
  ],
}
