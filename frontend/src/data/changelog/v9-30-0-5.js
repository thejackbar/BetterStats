export default {
  version: 'v9.30.0.5',
  date: '2026-08-18',
  sortKey: '2026-08-26T13:00:00Z',
  title: 'Sales Workspace: fixed the page jump on clicking a module pill',
  items: [
    'Clicking a module in "Interested in" (below the call Outcome dropdown) was visibly scrolling the whole page for a moment before settling. Traced to the site-wide smooth-scroll setting reacting to the reload behind the scenes — the admin app never needs that, so it\'s switched off there and the page now just stays put.',
  ],
}
