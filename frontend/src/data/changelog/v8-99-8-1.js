export default {
  version: 'v8.99.8.1',
  date: '2026-08-02',
  sortKey: '2026-08-02T00:00:00Z',
  title: 'Fixed "Active now" overstating live traffic',
  items: [
    'The Usage page\'s Live panel counted background heartbeat pings as "views" for the Active now tile, so a single visitor left idle on a page from a while ago could read as several fresh views "right now" with nothing matching in the feed below. Active now\'s views are now real page loads only, same as the other windows.',
  ],
}
