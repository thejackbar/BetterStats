export default {
  version: 'v9.19.10',
  date: '2026-08-11',
  // Must sort above v9.19.9's 2026-08-16T00:30:00Z key.
  sortKey: '2026-08-16T01:00:00Z',
  title: "Fix: BetterPosts scorecard had each side's own bowling under its own batting",
  items: [
    'The Scorecard post pulled from a match link showed each team\'s batting card followed by their OWN bowling figures, nonsense, since a team doesn\'t bowl to itself. It now shows the bowling of whoever actually bowled that innings, the way a scorebook reads: a team\'s batting, immediately followed by the figures of the side that dismissed them.',
    'The team that batted first is now always on the left, labelled 1st innings: previously this followed the ground\'s home/away side, which isn\'t the same thing (a team can bat first away from home, as the reported match had).',
  ],
}
