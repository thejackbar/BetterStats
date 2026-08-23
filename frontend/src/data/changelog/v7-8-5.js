export default {
  "version": "v7.8.5",
  "date": "2026-05-25",
  "sortKey": "2026-05-25T00:00:08Z",
  "title": "Mobile layout. Scorecards, StatLab, Yearbook & Forms",
  "items": [
    "Match Scorecard hero (Home / Result / Away strip) now fits on 390px-wide phones. Scores and team names scale down on mobile so 3-digit totals no longer overflow the column",
    "StatLab target tabs use horizontal scroll instead of flex-wrap (avoids the underline-indicator misalignment that wrap causes)",
    "Yearbook hero callouts (Players · Runs · Wickets · Record · Win Rate) shrink from text-5xl to text-3xl on mobile so \"21W 5D 6L\" no longer overflows",
    "Yearbook \"By the Numbers\" stat groups: 2 columns on mobile (was 4). Labels and values now have breathing room",
    "Yearbook tab strip picks up the pb-no-scrollbar treatment for clean horizontal scroll",
    "iOS form auto-zoom fix: inputs, selects and textareas now render at 16px on touch devices, so tapping a login field, search box or modal input no longer triggers a jarring zoom"
  ]
}
