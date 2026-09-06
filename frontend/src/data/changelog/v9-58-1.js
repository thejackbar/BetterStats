export default {
  version: 'v9.58.1',
  date: '2026-09-01',
  sortKey: '2026-09-01T20:00:00Z',
  title: 'Segment on whether a club is Won on the sales pipeline',
  items: [
    'Internal: a new Segments rule, "Sales pipeline stage" — Won, or anything but Won.',
    'Won reads the stage the deal actually sits in, not its status field, so a deal showing as Trial on the board never counts as won.',
    'Only BetterCricket’s own pipeline counts: a club that closed its own sponsorship deal is not a club we have sold to.',
    'An archived deal is off the pipeline, so it is off this rule too.',
  ],
}
