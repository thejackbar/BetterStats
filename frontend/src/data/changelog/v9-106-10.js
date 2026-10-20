export default {
  version: 'v9.106.10',
  date: '2026-10-05',
  sortKey: '2026-10-05T14:00:00Z',
  title: 'Fantasy: late scorecards now count, shared fixtures are scored, and My Team no longer runs off the page',
  items: [
    'Fixed: a player who had played could sit on 0 for good. A round is settled once it ends, but a scorecard can be finished, corrected or synced after that, and nothing looked at a settled round again. Each night, any round scored in the last fortnight is now checked against its scorecards and settled again if they have changed. Each team keeps the players it had in that round, so a transfer made since does not rewrite it, and no extra free transfer is given.',
    'The Fantasy overview now shows when a scored round is out of date: "Scorecards have changed since this was settled", with who scores differently and by how much. Press Settle on the round, or Settle due rounds, to bring it up to date straight away.',
    'Fixed: Fantasy now scores your players in a fixture the other club synced first. It used to find a club\'s games through the season they were stored under, so a match could drop out of your Fantasy depending on which club\'s sync got there first. A grade filter on your own grades now also matches the same grade under the other club, and the other club\'s players in the same match are no longer picked up.',
    'Fixed: the My Team page ran off the right edge on desktop. The "This round" and club ladder panel was cut off, and at some widths the whole page scrolled sideways. The player cards now wrap onto a new line rather than hiding behind a scroll, and the Wicketkeeper label is no longer cut off.',
    'If a scoring setting is changed, any round scored in the last fortnight follows the new setting the next time it is brought up to date. Older rounds stay as they were until you press Settle on them.',
  ],
}
