export default {
  version: 'v9.106.38',
  date: '2026-10-07',
  sortKey: '2026-10-07T06:00:00Z',
  title: 'Player profiles are kept out of search, and bulk collection is limited',
  items: [
    'Player profile pages are no longer listed in our sitemap, they ask search engines not to index them, and robots.txt tells crawlers to stay away. Club pages such as ladders and records are unchanged.',
    'Requests for profile pages and the data behind them are now limited per visitor, and known AI and bulk-scraping crawlers are refused on them. Normal browsing is not affected. A page requested very fast gets a short "please wait" message instead.',
    'Sharing a profile link still shows a preview card in Facebook, WhatsApp and similar apps.',
    'Bulk changes in BetterSelect, such as moving a whole group of players to a squad, are not limited.',
  ],
}
