export default {
  version: 'v9.19.6',
  date: '2026-08-11',
  // Must sort above v9.19.5's (future-dated) 2026-08-15T21:00:00Z key. The
  // real 2026-08-11 timestamp sorted this release BELOW v9.19.5, so it read
  // as older than the release it follows and SITE_VERSION stayed on v9.19.5.
  sortKey: '2026-08-15T22:00:00Z',
  title: 'BetterPosts: build a whole round from one match link',
  items: [
    'Fixtures and Results posts can now be filled from any one match link. Paste a link from the round and every grade\'s game that weekend comes in, even off-season or for a past round where the live feed has nothing.',
    'Fixtures and Results posts can spread across carousel pages. Pick a page count and the rows split evenly, with each page exported as its own slide.',
    'The fixtures and results rows can be dragged into order by their handle, on top of the existing arrows.',
    'Player of the Match posts fill from a match link too. We work out the player of the match from the scorecard, and you choose which of their batting, bowling and fielding stats go on the post.',
    'Pasting a playhq.com link anywhere now gets a clear note that BetterPosts pulls match data from play.cricket.com.au, with your club\'s recent matches offered so you can still pick the right game.',
  ],
}
