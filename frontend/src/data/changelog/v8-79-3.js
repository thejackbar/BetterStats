export default {
  version: 'v8.79.3',
  date: '2026-07-23',
  sortKey: '2026-07-23T16:00:00Z',
  title: 'Match scorecard: fixed the wrong team crest and opposition players tagged as fill-ins',
  items: [
    'On some matches, both team crests were showing the same club\'s logo, and most of the opposition lineup was wrongly tagged "FILL-IN" with a claim button, while a couple of them showed up as if they were our own registered players. Cause: a couple of the opposition\'s players had old stats stored under our club from a previous time they played for us, and that was enough to make the page think the whole opposition team was ours. Whichever club actually owns the page now always wins that call.',
    'Fixed the same underlying mix-up in the fall of wickets and partnerships sections, where it could show an opposition player\'s wicket or partnership under one of our own players\' names, or list the same wicket twice.',
  ],
}
