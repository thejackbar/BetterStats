export default {
  version: 'v9.139.4',
  date: '2026-11-04',
  // Above v9.139.3.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T23:00:00Z',
  title: 'Availability: the whole list scrolls with the page',
  items: [
    'Fixed: the Availability grid was boxed to the height of the window, so with the filters open you could see about three players at a time. The list now runs down the page and you scroll the page to see everyone.',
    'The row of dates stays pinned under the top bar as you scroll, and it moves sideways with the grid.',
    'New: "Include inactive players" and "Include dormant players" in the Filters panel. Current squad hides both, and the only way back was switching the whole roster to All. Each one now adds its group back on its own, and the chip above the grid takes it out again.',
  ],
}
