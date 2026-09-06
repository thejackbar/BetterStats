export default {
  version: 'v9.65.1',
  date: '2026-09-08',
  sortKey: '2026-09-10T10:00:00Z',
  title: 'Every strike rate is worked out from the innings that recorded a ball count',
  items: [
    "A player profile's six-axis Player Profile card was reading a strike rate far too high — it divided every run a batter had made by the balls from the innings somebody had typed a ball count into. It now reads the same figure the career header above it already had right, and says how many innings answered it.",
    'The same correction reaches the rest of the app: the captain panel, the teammate comparison, the BetterIQ player deep dive, the team analysis boards, the opposition scouting report and StatLab’s family reports. Runs, wickets, averages and every other figure still count every innings — only the rate changes source.',
    'A rate drawn from fewer innings than the figures beside it carries a small dagger and a line saying which innings it came from. Nothing is marked where the figures are complete.',
    'Bowling economy on the captain panel and in StatLab was adding overs up as written, so 10.2 and 10.2 came to 20.4 rather than 20 overs and 4 balls. Both convert to balls first now.',
    "The SR column in a player's Innings History was empty on every row, including innings that did record a ball count. It now shows that innings' own strike rate, and still shows a dash where no ball count was recorded.",
  ],
}
