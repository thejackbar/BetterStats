export default {
  version: 'v9.27.4',
  date: '2026-08-17',
  sortKey: '2026-08-23T05:00:00Z',
  title: 'Sales Workspace: state filter, contact search, sorting, and a tidier filter bar',
  items: [
    'New State filter (multi-select, e.g. WA and NSW at once) alongside the existing filters.',
    'Current trials and Expired trials are now their own checkboxes, not just options buried in the Stage picker.',
    'Search now also matches a contact\'s name, not just the club\'s: typing "Pat Smith" finds the club Pat is the secretary of.',
    'A new Sort control above the queue: Recommended (the existing priority order), Recent, Club name, Engagement score, or Trial days, each with a ▲/▼ to flip the direction. Trial days covers current and expired trials together: an expired trial\'s "days ago" is a negative number, so a trial that just lapsed sits right next to one about to lapse.',
    'The filter bar is now grouped into labelled sections (Search, Pipeline, Call status, Engagement & location, Interested in, Source) instead of one long row of controls.',
  ],
}
