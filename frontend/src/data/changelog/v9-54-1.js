export default {
  version: 'v9.54.1',
  date: '2026-08-29',
  sortKey: '2026-08-29T09:00:00Z',
  title: 'Two-day matches show both innings, and an uploaded scorecard opens',
  items: [
    'A two-day match now shows all four innings. The page had only ever drawn the first two, so each side’s second innings was missing even though the data was there all along.',
    'The header reads the way a scorecard is written: "31 & 128" for a side that batted twice.',
    'The result is worked out across both innings. The reported grand final read "won by 71 runs" off the first innings alone; it correctly says "won by 7 wickets" now.',
    'The winner is marked on both of that side’s innings, and never on the other side’s.',
    'A one-day match is unchanged, and an innings victory is named as one.',
    'Fixed: a scorecard uploaded from a photo or PDF appeared in the Games list and then failed to open with "Internal Server Error". Every uploaded card was affected, on every club. They open now, with both teams, their totals, the fall of wickets and the partnerships.',
  ],
}
