export default {
  version: 'v8.91.0',
  date: '2026-07-29',
  sortKey: '2026-07-29T23:00:00Z',
  title: 'CRM pipeline: Active Trials, New Deals and New Deal Activity filters, plus an engagement trend arrow',
  items: [
    'New "Active Trials" filter shows every deal with at least one module on a live trial, whatever stage the card is in.',
    'New "New Deals" filter narrows the board to cards created today or within a date range, based on when the deal card was added.',
    'New "New Deal Activity" filter shows cards that had something happen in the window: a stage promotion (by hand or automatic), a page view, a trial or subscription started, cancelled or paused, or an onboarding step completed.',
    'The "New Deals" and "New Deal Activity" date filters, and the engagement arrow\'s day-over-day comparison, all read calendar days in Perth (Western Australia) time.',
    'The "Trial expired" filter is now labelled "Expired Trials".',
    'Deal cards show a green up-arrow next to the engagement score when it rose from yesterday, or a red down-arrow when it fell. No arrow means it did not change.',
    'The pipeline now refreshes on its own every 45 seconds and the moment you switch back to the tab, so a deal, promotion or score that changed in the background shows up without a manual reload.',
    'New "Recalculate" button recomputes every club\'s engagement score and re-runs auto-promotions in the background, then updates the board as it goes.',
  ],
}
