export default {
  "version": "v7.28 Beta",
  "date": "2026-05-29",
  "sortKey": "2026-05-29T22:00:00Z",
  "title": "Fee Tracking polish: per-day Mark Paid, bulk payments, cleaner tables",
  "items": [
    "Match-day rows on the member page now have a 'Mark Paid' button that logs a payment of (days × tier rate) in one click. Each row shows a PAID / UNPAID pill and an UNMARK button to reverse it. Removed the override-reason text box",
    "New Bulk Payment page (/admin/fees/payments/bulk): one deposit covering multiple players. Pick the bank deposit details once, add players, tick which unpaid match days each player is paying for, and commit. Creates one payment per player with all selected match days marked Paid",
    "Members table is now a proper HTML table. Days / Payable / Paid / Owed / Status columns line up cleanly with right-aligned tabular numbers. Same treatment for the Payments ledger and Match Days table",
    "Bulk tier (Phase 3) is now hinted directly above the Members table: tick rows to set a tier on many members at once, perfect for graduating a batch of students",
    "Match-day rows are frozen once a payment is logged against them. The weekly recompute won't silently bump the days or remove the row"
  ]
}
