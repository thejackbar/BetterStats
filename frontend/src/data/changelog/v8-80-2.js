export default {
  version: 'v8.80.2',
  date: '2026-07-24',
  sortKey: '2026-07-24T18:00:00Z',
  title: 'Scorecard reader gets smarter about names written across the pages',
  items: [
    'A player is written many times on a scorecard, and often more clearly in one spot than another. The reader now cross-references every place a name appears and uses the clearest version everywhere, so a bowler who looks like "S Willingslow" in the dismissals column but is plainly "G Wittingslow" in the bowling figures below comes through as one name, not two.',
    'The bowling figures are treated as the source of truth for bowler names, and the batting order for batter names, without ever merging two different players who just share a surname.',
    'If a wicket is credited to a bowler whose name isn\'t in that innings\' bowling figures, the review screen now flags it as a likely misread to reconcile.',
  ],
}
