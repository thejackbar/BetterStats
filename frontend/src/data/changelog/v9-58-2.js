export default {
  version: 'v9.58.2',
  date: '2026-09-01',
  sortKey: '2026-09-01T21:00:00Z',
  title: 'Segment rule values are no longer case sensitive',
  items: [
    'Internal: a Segments rule written as "WON" or "Won" now means the same as "won", on the sales pipeline, club primary admin and club trial rules.',
    'This mattered more than it looked: a value the engine did not recognise dropped the rule entirely, so the segment widened to everyone instead of narrowing.',
    'The Won test itself was never case sensitive — it reads the stage’s own Won flag, so a stage named "Closed Won" always worked.',
  ],
}
