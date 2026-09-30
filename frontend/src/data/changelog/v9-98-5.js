export default {
  version: 'v9.98.5',
  date: '2026-10-05',
  // Above v9.98.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-05T13:00:00Z',
  title: 'Resetting BetterStats no longer switches the club’s public site back on',
  items: [
    'All Clubs > Reset on BetterStats used to remove its row, and the platform reads a club with no BetterStats row as an old club that is always live. So the public site and stats tools came straight back. Reset now leaves BetterStats not live but with no trial history, so the club is eligible for a new trial and stays offline until one starts.',
    'Self-serve registration now accepts a club that has been reset, has nobody administering it and has nothing paid. Before, searching for it sent you to its public page as "already registered". A club with an admin, a paid module or a Stripe subscription is still treated as taken.',
    'A club that was already reset before this change still has no BetterStats row. Start a BetterStats trial on it, then Reset again, to put it in the new state.',
  ],
}
