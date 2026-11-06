export default {
  version: 'v9.129.31.1',
  date: '2026-10-26',
  // Above v9.129.31's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T21:00:00Z',
  title: 'Milestone posts show the whole name and the date of a games milestone',
  items: [
    'Fixed: on the Milestone Cards post, a long first name ("Sandeep Reddy") ended in "..." and some surnames were cut off along the bottom of the card. The number is now sized to leave room for the name, and a long first name shrinks to fit.',
    'Fixed: a "Games in" milestone (50 games in PSWL South A, say) had no date, so it showed "no date" in the picker and was left out of every window except All time. It now carries the date of the game that reached it.',
  ],
}
