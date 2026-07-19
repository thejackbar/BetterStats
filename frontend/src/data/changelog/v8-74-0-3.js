export default {
  version: 'v8.74.0.3',
  date: '2026-07-19',
  sortKey: '2026-07-19T16:00:00Z',
  title: 'Fixed the trial signup modal opening truncated near the top of the page',
  items: [
    'The "Request access" button in the marketing nav bar opened the 14-day trial signup modal inside the nav bar itself, which switches on a background blur once you scroll (or on any non-home page). A blurred ancestor becomes the positioning frame for a fixed-position overlay, so the modal was pinned to the nav bar\'s own sliver of height instead of the full page and got clipped at the top. The modal now always mounts at the page root, so it centres in the viewport no matter which button opened it.',
  ],
}
