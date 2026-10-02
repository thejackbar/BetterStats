export default {
  version: 'v9.102.6',
  date: '2026-10-02',
  sortKey: '2026-10-02T01:00:00Z',
  title: 'A hidden player stays hidden, and a player who asks to be removed can be',
  items: [
    'A player set to Hidden now stays hidden across the whole public site. Before, their profile page stopped loading but their stats could still be fetched directly, they stayed in the sitemap, and search and social previews could still show their name and photo. All three are closed.',
    'When a player asks to be taken off the public website, BetterSports can now record that request. The player stays hidden, their photos are deleted (including the BetterIQ scouting copy), and the club can no longer switch them back on, upload a photo for them or bring them back by importing a sheet. Their matches stay in your records and totals.',
    'On a player\'s profile in your admin, someone removed at their own request shows a short note in place of the Hidden switch.',
  ],
}
