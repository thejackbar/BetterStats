export default {
  version: 'v1.0.7 Beta',
  date: '2026-05-31',
  sortKey: '2026-05-31T15:00:00Z',
  title: 'Social Post: dynamic text sizing + editable headline',
  items: [
    "Player names now auto-shrink to fit on a single line across the lineup templates (T1–T6). Very long names like 'WARDELL-JOHNSON' or longer no longer wrap onto multiple rows or get clipped: they scale down just enough to fit, while short names stay full-size.",
    "The big lineup headline (previously the fixed word 'SQUAD' on T1) is now editable and auto-sizes to fit on up to two lines, so it never clips. Set it in Match Info → Headline.",
    "When you open a Social Post from a saved XI in BetterSelect, the headline auto-fills with the team/grade name (e.g. 'Applecross 6th XI').",
    "Verified end-to-end in headless Chrome, including the export, with deliberately extreme name lengths.",
  ],
}
