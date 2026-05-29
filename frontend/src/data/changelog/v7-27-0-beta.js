export default {
  "version": "v7.27 Beta",
  "date": "2026-05-29",
  "sortKey": "2026-05-29T20:00:00Z",
  "title": "Fee Tracking (Phase 3) — season rollover, bulk tier, bank CSV import",
  "items": [
    "Season rollover: one click opens this season for every member from the previous one, with tiers carried across by name. Skips 'Left Club' tiers and members already on the new season",
    "Bulk tier edit: tick rows in the Members table → a floating action bar appears → 'Set tier' applies the chosen tier to every selected member (and carries it forward as their default for next year). Perfect for graduating a batch of students to Senior",
    "Import bank CSV: upload a statement, the parser auto-detects Date/Amount/Description across CBA/NAB/ANZ formats, fuzzy-matches each credit row to a member with a confidence score. Rows ≥ 85% confidence auto-select, you confirm the rest, then commit them all in one go",
    "Debit rows and negative amounts are ignored, and the cleaned description is saved as the payment's bank ref"
  ]
}
