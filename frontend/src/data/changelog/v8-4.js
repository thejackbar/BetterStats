export default {
  "version": "v8.4",
  "date": "2026-06-06",
  "sortKey": "2026-06-06T10:00:00Z",
  "title": "KlubPro migration tooling (super-admin onboarding)",
  "items": [
    "New Super Admin tool to bring a club's KlubPro data into BetterStats: a review wizard that matches players by name and fills in profile details (gender, contact, role, batting/bowling, skills, photo)",
    "Field-level approval. Each player card shows BetterStats vs KlubPro side by side (both photos + details), with a Fields panel of per-field checkboxes so you can approve the match but skip individual fields. Every field KlubPro has data for is ticked by default (including the photo); untick the photo to keep your existing one. A blank KlubPro value never overwrites an existing BetterStats value",
    "Bulk Approve reviewed players in one action, respecting each player's own field choices, with a summary (fields migrating/skipped, image replacements) before you confirm",
    "Clearer two-step flow: approving a player records your choices; clicking Import is what actually writes them to BetterStats. Cards now show APPROVED · NOT IMPORTED vs IMPORTED ✓, with counts and a prompt so nothing is left un-imported by mistake",
    "Imported batting hand, bowling type and profile photo now show correctly in the admin. These were being stored in KlubPro's label format instead of BetterStats' codes (and the photo wasn't linked for the admin editor). Re-import a club brought across earlier to fix it",
    "Rejecting a wrong match now frees that KlubPro player so you can approve them against the correct BetterStats player, and the name search ignores double spaces / Jnr-Snr suffixes / word order so players with an (empty) middle name are found",
    "Newly-mapped clubs now auto-suggest matches by name in the tool (previously only four pilot clubs had matches generated, so everyone else showed 'no match'). Unique names are suggested ready to approve; players with two same-name candidates are flagged 'needs review' instead of guessing",
    "Map any staged KlubPro club to a BetterStats organisation right from the dashboard: pick the club in the 'Mapped to' dropdown, confirm, and it saves instantly (works for any club added to BetterStats in future, no manual setup)",
    "Sponsor import with logo previews and one-tick selection, with built-in protection against importing the same sponsor twice",
    "Every import shows a dry-run preview first, takes a backup, and can be rolled back with one click from the History tab"
  ]
}
