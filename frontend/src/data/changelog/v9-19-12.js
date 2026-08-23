export default {
  version: 'v9.19.12',
  date: '2026-08-11',
  sortKey: '2026-08-16T02:00:00Z',
  title: 'Scorecard posts: fixed both teams showing as one team',
  items: [
    'Fixed a bug where the Scorecard tab could show the same team on both sides with 0/0 and empty batting/bowling. Happened when Grassroots briefly returns a match mid-correction with its innings wiped. That snapshot is no longer cached, so the next load retries instead of getting stuck on it.',
    'Even when a match genuinely has no innings data at all, the two sides are now guaranteed to show as two different teams rather than the same one twice.',
  ],
}
