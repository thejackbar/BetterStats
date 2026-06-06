export default {
  "version": "v8.4",
  "date": "2026-06-06",
  "sortKey": "2026-06-06T10:00:00Z",
  "title": "KlubPro migration tooling (super-admin onboarding)",
  "items": [
    "New Super Admin tool to bring a club's KlubPro data into BetterStats: a review wizard that matches players by name and fills in profile details (gender, contact, role, batting/bowling, skills, photo)",
    "Field-level approval — each player shows BetterStats vs KlubPro side by side with a checkbox per field, so you can approve the match but skip individual fields (e.g. keep your newer profile photo while migrating email and mobile). Smart defaults pre-tick the right boxes and never overwrite a value with a blank",
    "Bulk Approve reviewed players in one action — respecting each player's own field choices — with a summary (fields migrating/skipped, image replacements) before you confirm",
    "Map any staged KlubPro club to a BetterStats organisation right from the dashboard — pick the club in the 'Mapped to' dropdown, confirm, and it saves instantly (works for any club added to BetterStats in future, no manual setup)",
    "Sponsor import with logo previews and one-tick selection, with built-in protection against importing the same sponsor twice",
    "Every import shows a dry-run preview first, takes a backup, and can be rolled back with one click from the History tab"
  ]
}
