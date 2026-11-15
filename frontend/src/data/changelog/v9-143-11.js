export default {
  version: 'v9.143.11',
  date: '2026-11-15',
  // Above v9.143.10.2's sortKey (2026-11-20T17:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T18:00:00Z',
  title: 'Compare: overs, best figures and extras on the Bowling tab',
  items: [
    "The Bowling tab on the Compare page now shows overs bowled, runs conceded, wides, no balls and total extras. Overs and runs conceded are shown without green or red, since neither end is better.",
    "Best figures now read as the actual spell, like 5/28, where they used to show just the wicket count. The best spell is the one with the most wickets, and the fewest runs breaks a tie. A player with only a wicket count on file shows \"4 wkts\".",
    "Overs add up in cricket notation, so two seasons of 10.4 overs read 21.2 overs.",
    "Where the scorer never counted wides or no balls, the table shows a dash and leaves that player out of the green and red. A note under the table says so.",
  ],
}
