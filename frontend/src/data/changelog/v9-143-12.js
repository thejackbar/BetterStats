export default {
  version: 'v9.143.12',
  date: '2026-11-15',
  // Above v9.143.11.1's sortKey (2026-11-20T19:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T20:00:00Z',
  title: 'Share card: new stat line and club rankings on the back',
  items: [
    "The band along the bottom of the player share card now shows the same six figures every time: Matches, Runs, Batting Av, Wickets, Bowling Av and Dismissals. High score and Catches have come off it (both are still on the back).",
    "All six figures are the same size. The size follows the longest figure on the card, so a big career total shrinks the row a little instead of one number looking bigger than the rest.",
    "A figure the player has none of reads a dash, like a batter's bowling average. Dismissals is catches, run outs and stumpings together.",
    "The back of the card now lists every club ranking where the player is in the top 100: matches, runs, batting average, wickets, bowling average, dismissals and catches. A ranking past 100 is left off.",
    "Averages are ranked among players with at least 10 innings (batting) or 10 wickets (bowling), so one good afternoon does not top the board. A figure of zero is never ranked.",
    "The sheet on the back is a little tighter to make room for the rankings.",
  ],
}
