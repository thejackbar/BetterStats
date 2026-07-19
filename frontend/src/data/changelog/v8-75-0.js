export default {
  version: 'v8.75.0',
  date: '2026-07-19',
  sortKey: '2026-07-19T17:00:00Z',
  title: 'Usage tracking: session duration, time on page, visitor journeys, and a UTM-campaign capture fix',
  items: [
    'The Usage page never tracked how long a visitor actually stayed on a page or the site. A new "Engagement" panel shows average and median session length, a session-length distribution, and average time on page per page, all derived from a new page_exit beacon fired when a visitor navigates away, backgrounds the tab, or closes it.',
    'Typing (or deep-linking with) a visitor\'s id into the Usage page search now shows their "Visitor journey": the actual ordered sequence of pages they viewed, split into visits, with per-page dwell time and whatever campaign tag was attached to each step.',
    'Fixed two related gaps in campaign attribution. A club outreach link whose template hand-placed {{utm_source}} was silently losing its utm_campaign tag on send. A returning visitor clicking a new campaign link could also have that click recorded under a stale, older campaign instead of the one they had just clicked.',
  ],
}
