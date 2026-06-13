export default {
  version: 'v8.15.3',
  date: '2026-06-13',
  sortKey: '2026-06-13T06:00:00Z',
  title: 'BetterIQ Season + Team filters now work by real cricket season',
  items: [
    'The Season filter is now keyed on the real cricket season, not one database row. A club\'s "2024/25" is often stored as several rows (separate competitions, plus the older MyCricket and newer PlayHQ feeds give the same year different ids), so picking a year used to show only a slice of it on Team analysis, Match review and the phase charts. Picking a season now covers every row for that year, the same way Player trends already did.',
    'Added a plain "This season / All seasons / Compare" toggle to the filter bar. "All seasons" is a true all-time view; "This season" is the current year; "Compare" sets a span across years for the trend charts.',
    'The season picker lists each year once instead of repeating it, and the Grade dropdown now offers every grade the club fielded that year (grades attached to a sibling season row were going missing).',
    'Match review now follows the global Season + Team filter; it was ignoring it before.',
  ],
}
