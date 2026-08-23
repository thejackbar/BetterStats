export default {
  version: 'v9.27.2',
  date: '2026-08-17',
  sortKey: '2026-08-23T03:00:00Z',
  title: 'A season in your sheet can no longer be filed under the wrong year',
  items: [
    'Fixed: when Import Stats met a season your club does not hold yet, it could quietly accept a different one. Season names differ by a couple of digits, so "Summer 2020/21" read as an 86% match for "Summer 2023/24" and was taken without asking. A club\'s early history landed on recent years and their totals came out well above their own records.',
    'A season label that names its own year now only ever matches that year. Nothing else is offered, and a year the club holds twice asks you to pick rather than choosing for you. Short forms like "18/19" and "2018-19" still match Summer 2018/19 as before.',
    'The review screen now names any season in your sheet that does not exist yet, and says what happens if you leave it: the figures still count towards each player\'s career, but they arrive as one "Prior Seasons & Adjustments" line instead of their own seasons. Create them on the Seasons step to keep the year.',
    'If you have already imported a sheet with seasons your club was missing, undo that import from the panel at the bottom of Import Stats, create the seasons, and import again.',
  ],
}
