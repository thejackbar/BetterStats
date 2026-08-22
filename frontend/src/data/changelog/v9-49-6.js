export default {
  version: 'v9.49.6',
  date: '2026-08-23',
  sortKey: '2026-08-23T09:00:00Z',
  title: 'A linked club is scrolled to in the call queue, and clearing every interest pill clears the value',
  items: [
    'Opening a club from a ?club= link — the Sales Commissions and Sales Performance drill-downs both build them — now scrolls the call queue to that club and highlights its row, instead of leaving it correctly selected somewhere far down a list nobody moved.',
    'A linked club that the current filters exclude has no row to select, so the queue now says so and offers to clear the filters and bring it in.',
    'Fixed: clearing every "Interested in" pill left the old dollar figure on the deal, so it could read "no modules" beside a four-figure value. The value now follows the selection all the way down to nothing.',
  ],
}
