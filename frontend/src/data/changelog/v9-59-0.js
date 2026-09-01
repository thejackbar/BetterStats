export default {
  version: 'v9.59.0',
  date: '2026-09-01',
  sortKey: '2026-09-01T12:00:00Z',
  title: 'Strike rates and economies read only the innings that recorded the balls',
  items: [
    'A strike rate needs runs and balls faced from the same innings. Plenty of cricket is still scored in a written book, and older records rarely recorded balls faced at all, so a season could hold every run a batter made and a ball count for only some of those innings. Dividing all the runs by some of the balls gave figures far too high: 500 runs off a recorded 150 balls read as a strike rate of 333.',
    'Every strike rate and economy in the app is now worked out from the innings and spells that recorded both halves, and says which ones answered it. A figure built from part of a season carries a small mark, and the note beside it explains what is missing. Runs, wickets, averages and everything else still count every innings.',
    'Where a season reached us as totals only, with no scorecards behind it, the figure it came with still stands and the page says where it came from rather than going blank.',
    'The batting leaderboard can now be sorted by strike rate, and both it and the economy board let you set how many recorded innings a player needs before they are ranked. Your club can set its own default under Club Settings.',
    'Records now keeps a best strike rate and best economy for a season, rather than all time. How much was written down changed from one era to the next, so a single career-long figure could not be stood behind; for a range of seasons, StatLab takes as many as you like at once.',
    'Fixed while here: a bowling economy worked out from overs in cricket notation was slightly off wherever a spell ended mid-over, since 10.2 plus 10.2 is not 20.4 overs.',
  ],
}
