export default {
  version: 'v9.129.18',
  date: '2026-10-25',
  // Above v9.129.17's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T05:00:00Z',
  title: 'Fantasy: running scores while a round is being played',
  items: [
    'New: Fantasy scores now update while the games are being played. Every 10 minutes during the day, the games Cricket Australia has not finished are read again, and each player\'s points, each team\'s round score and the ladder move with them. A two day round shows running points from its first day instead of nothing until the round ends.',
    'The Fantasy overview has a Sync scores button to do it right now, a Live scoring switch to turn the automatic refresh off for the season, and a line on each running round saying when its scores were last checked. The Live screen managers see shows the same time.',
    'Settle is now called Confirm final scores. Running points are provisional: confirming a round is still what banks the free transfer, fills head-to-head results and moves prices. Confirming a round that is still being played asks first.',
    'Fixed: a game stored while Cricket Australia still had it in play kept the figures it was first read with (a batter on 1 not out stayed on 1) until the card was marked complete. A running game is now kept up to date, and its final figures land as soon as it finishes instead of waiting for the next results sync.',
  ],
}
