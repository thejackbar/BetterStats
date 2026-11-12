export default {
  version: 'v9.143.5.2',
  date: '2026-11-12',
  // Above v9.143.5.1's sortKey (2026-11-20T00:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T01:00:00Z',
  title: 'Meta ad clicks no longer show as our outreach email',
  items: [
    "Clubs that arrived from a Meta ad were showing as Email (our outreach) when their link carried a campaign id. The where-from label now reads the Meta tags first, so utm_source=meta or a paid_social medium is a Meta ad.",
    "Our outreach email is still Email. A link with a club code and no Meta tag keeps its label, and so does an email link that picked up a Facebook click id in an in-app browser.",
    "A medium of sales_email now counts as email even with no club code on the link.",
  ],
}
