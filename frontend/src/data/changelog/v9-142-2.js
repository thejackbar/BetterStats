export default {
  version: 'v9.142.2',
  date: '2026-11-10',
  // Above v9.142.1's sortKey (2026-11-19T05:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T06:00:00Z',
  title: 'Fantasy: rounds that no longer run on for weeks, plain names for the score buttons',
  items: [
    'Fixed: Fantasy rounds no longer run on for weeks. A club whose two day games start on alternate Saturdays had every week joined into one round. Sunbury\'s Round 4 ran from 30 October to 20 December, so managers could not change their team for seven weeks and the round could not be confirmed until the end. A round longer than two weeks is now cut back into one round per club weekend. Rounds that were already right are unchanged, and a round that has not been confirmed moves to the new dates overnight.',
    'Fixed: a 12th man who never took the field no longer gets the 4 point appearance score in Fantasy, and neither does someone who pulled out before the game. A substitute who took a catch still gets it.',
    'Settle is now Confirm final scores, and Unsettle is now Reopen round. Rounds read confirmed or reopened, and a short panel above the rounds says what Sync scores, Confirm final scores and Reopen round each do. Sync scores and Confirm final scores are proper buttons on every round. A round that is over and waiting says so, and says which button to press.',
    'New for support: a Fantasy health check, python -m app.scripts.fantasy_audit followed by a club or all. It lists rounds that are too long or off the draw, games that fall in no round, a round hiding the ones after it, players whose points differ from their scorecards, and pool players with no games. It only reads.',
  ],
}
