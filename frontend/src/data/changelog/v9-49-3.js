export default {
  version: 'v9.49.3',
  date: '2026-08-22',
  sortKey: '2026-08-23T04:00:00Z',
  title: 'A ?club= link opened the Sales Workspace on the wrong club',
  items: [
    'Fixed: clicking a club from Sales Commissions (or any other ?club= link) built the right URL but the Workspace then reassigned the selection to the top of the call queue, so it opened on a different club entirely.',
    'The cause was the queue treating a linked club that the current filters exclude as one that had dropped out of the queue and needed advancing past. A club named by the URL was never in the queue to begin with, which is a different thing, and it now stays selected.',
    'Picking a club from the queue by hand takes over from the link, so the usual "advance to the next club" behaviour comes back after that.',
  ],
}
