export default {
  version: 'v9.51.3',
  date: '2026-08-22',
  sortKey: '2026-08-23T07:00:00Z',
  title: 'Fixed: a club in the Sales Workspace that loaded forever and then failed',
  items: [
    'Opening a club sat on “Loading…” and eventually said “Could not load this club”. The drawer was working out the engagement score and the website analytics inside the same request that fetched the club, and on a club with real history behind it those two reads take long enough to outlast the request itself.',
    'They have their own request now, fired after the pane has rendered — the same thing the club’s map already did. The drawer opens straight away and the two panels fill in behind it.',
    'The deeper cause: when one of those reads failed it was quietly ignored, but the failure left the database transaction aborted, so everything the request did afterwards failed too. Every best-effort read in the Sales Workspace now rolls back before carrying on, which also stops one broken card on the origin panel emptying the two beside it.',
  ],
}
