export default {
  version: 'v9.52.2.1',
  date: '2026-08-24',
  sortKey: '2026-08-24T18:00:00Z',
  title: 'Picking a module in Sales Workspace no longer moves the page',
  items: [
    'Fixed: clicking a pill under "Interested in" jumped the page, taking the club pane — and the pill just clicked — out from under the cursor. The queue was pulling the open club\'s row back into view on every save, which scrolls the whole page when that row sits above the fold. Picking a module is not navigating to something, so it now leaves the view exactly where the rep put it.',
    'The queue itself still refreshes behind the click, so the module change shows up on the club\'s row as before.',
  ],
}
