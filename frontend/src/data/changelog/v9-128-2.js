export default {
  version: 'v9.128.2',
  date: '2026-10-20',
  // Above v9.128.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-05T14:00:00Z',
  title: 'A club\'s teaser link can be found from its UTM code or its Cricket Australia id',
  items: [
    'Every club\'s teaser link is now tied to the club in one place, so a UTM code, the id the club search on /trial returns, or the token itself each lead to the same club.',
    'A code or id that more than one club shares, or that a club does not have, finds nothing rather than the wrong club\'s season. A club that has already registered is never matched.',
    'New read-only report, report_club_teaser_links, shows how many clubs can be reached by UTM code and by Cricket Australia id, and lists the ones that cannot.',
  ],
}
