export default {
  version: 'v9.74.0',
  date: '2026-09-09',
  // Above v9.73.0's sortKey, which origin/main still has as the highest, or
  // SITE_VERSION never reaches this one. Check origin/main at merge time.
  sortKey: '2026-09-21T06:00:00Z',
  title: 'BetterPosts: every layout is drawn at the post size, and a block can go behind it',
  items: [
    'Every built-in layout now draws itself at 1080×1350 portrait and 1080×1920 story, instead of sitting whole in the middle with bands above and below. A fixture list spreads its rows down the taller post, a poster gives its photo the extra room, and headers and footers stay on the edges where they belong.',
    'Because the layouts fill the canvas themselves, the Fit whole / Fill & crop choice is gone — it only ever described a band that no longer exists.',
    'A block you add can now be sent BEHIND the layout, not just moved among the other blocks you have added. Select it and press "Send behind", or press Backward past the bottom of the stack; the layout\'s own background stops painting so the block shows through.',
    'The Layers panel lists the layout itself as a row, so what is over it and what is behind it is visible at a glance, and a block behind the layout can still be dragged around on the canvas.',
    'A link that names a layout (?template=) now opens on that layout. It skipped the "What are you posting?" screen already but then showed whichever layout was last used.',
  ],
}
