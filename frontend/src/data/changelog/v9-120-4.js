export default {
  version: 'v9.120.4',
  date: '2026-10-23',
  // Above v9.120.3.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-23T11:00:00Z',
  title: 'Results posts show your own bowlers, and a lapsed players filter',
  items: [
    'Fixed results posts that listed the opposition\'s bowlers under your club. Wrap + Leaders, the Final Score posts, the Glass Card and the scorecard block on the Blank canvas now show your own bowling figures next to your own batters.',
    'Wrap + Leaders has a new Players shown switch, Our club or Opposition. The heading on the post says which one it is. Pull the round again to load the opposition\'s figures for matches you had already pulled.',
    'The recency dropdown on the BetterSelect Players page and the squad lists has a new group, Last played more than 1, 2, 3, 5 or 10 years ago, next to the Played within choices. It is for finding players who have not played for a while. A player who has never played is not counted as lapsed, so use the Never played filter for them.',
  ],
}
