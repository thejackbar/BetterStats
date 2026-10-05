export default {
  version: 'v9.106.29',
  date: '2026-10-05',
  sortKey: '2026-10-05T23:00:00Z',
  title: 'People who ask to be removed are no longer collected, and their old page says it is gone',
  items: [
    'A person who asks to be removed from BetterCricket is now left out of every sync, including a Full Rebuild. Before, they were hidden from the site but each sync still wrote their season totals and match lines, and kept their name on fall-of-wicket, partnership and fielding rows. Those rows stay in the card with the name blank.',
    'The old address of a removed person\'s profile now answers "gone" and tells search engines not to index it. It used to load the normal page, which left it sitting in search results.',
    'Player and scorecard data on the public site is now rate limited for each visitor, so one visitor cannot pull profile after profile in a few seconds. Ordinary browsing, including a whole walk through a profile\'s tabs, is not affected.',
    'The automatic merge of a hand-added player now leaves alone any name that belongs to someone who asked to be removed.',
  ],
}
