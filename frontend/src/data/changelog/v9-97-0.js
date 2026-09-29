export default {
  version: 'v9.97.0',
  date: '2026-09-28',
  sortKey: '2026-10-04T09:00:00Z',
  title: "Imported scorebook matches show the opposition, the score and the partnerships",
  items: [
    "The match CSV import takes the opposition's innings total, each innings' extras, and the score each batter fell at. A match imported this way shows both teams and both scores, not just your own side.",
    'Your bowlers now appear bowling at the opposition, not in your own batting innings.',
    'Partnerships are worked out from the fall of wickets and the batting order, including the unbroken stand at the end, and they appear on the match page and in Highest Partnerships. An innings whose fall of wickets does not line up with the batting order keeps its fall of wickets and gets no partnerships, rather than stands credited to the wrong pair.',
    'A scorebook that never recorded who batted first, or which side was at home, no longer shows "Innings 1", "Home" and "Away", or a winning margin worked out from an order nobody recorded. The match page names each side and says why.',
    'Older sheets without these columns import exactly as before.',
  ],
}
