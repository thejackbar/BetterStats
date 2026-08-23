export default {
  "version": "v7.17.1",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:31Z",
  "title": "StatLab: multi-select Season and Grade filters",
  "items": [
    "Season and Grade in the Customise Query → Context panel are now multi-select checkbox pickers. Pick any combination of seasons (e.g. 2022/23, 2023/24, 2024/25) plus any combination of grades (e.g. 2nd and 3rd grade) and every StatLab report respects the union.",
    "Each picker shows the selected count, a search box (handy for clubs with 50+ seasons), and a Clear button.",
    "URL encoding: selections are saved as ?c_season_ids=a,b,c&c_grade_ids=x,y. Saved-report URLs round-trip cleanly. Old URLs using the legacy single-select ?c_season_id= / ?c_grade_id= still work; the picker pre-fills from them on load and switches to multi-select the moment you touch it.",
    "Backend: new season_ids / grade_ids context keys with IN-list SQL expansion. Season multi-select still expands aliases (e.g. selecting \"Summer 23/24\" also picks up any alias seasons mapped to it)."
  ]
}
