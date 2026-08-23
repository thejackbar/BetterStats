export default {
  "version": "v7.9",
  "date": "2026-05-25",
  "sortKey": "2026-05-25T00:00:11Z",
  "title": "Merge Seasons. Combine split-year seasons into one",
  "items": [
    "Admin → Seasons has a new \"Merge Seasons\" tool. Pick a variant (e.g. \"Summer 2025/26\"), pick the canonical to keep (\"2025/26\"), merge. The variant is hidden from the public season dropdown and its stats roll up into the canonical everywhere: leaderboards, player profiles, career stats, records page",
    "Soft merge: no rows are rewritten, the per-season data stays exactly where it is, the merge is a thin alias mapping. Fully reversible from the Merge History panel. Undo and the variant reappears with all stats intact",
    "Player profile season-by-season now collapses merged seasons into a single row with summed counts and recomputed averages, so \"2025/26\" shows one combined row instead of two rows for Summer/Winter"
  ]
}
