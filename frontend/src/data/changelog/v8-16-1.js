export default {
  version: 'v8.16.1',
  date: '2026-06-13',
  sortKey: '2026-06-13T08:00:00Z',
  title: 'BetterIQ: merge sponsor-named grades, fix the career window label',
  items: [
    'The Grade filter now treats sponsor-named grades as one. Cricket Australia renames a grade with each season\'s sponsor ("B Grade" one year, "B Grade (DXC Technology)" the next), which used to list the same grade several times; the dropdown now shows "B Grade" once and picking it covers every sponsor variant. Numbered sub-grades like "(Div 1)" stay separate.',
    'Fixed the opposition career table that still said "Last five years" after the window was widened to ten. It now reads "Season by season" and the heading shows the real span (for example, 2016 to 2025).',
  ],
}
