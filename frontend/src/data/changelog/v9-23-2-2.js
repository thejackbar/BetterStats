export default {
  version: 'v9.23.2.2',
  date: '2026-08-14',
  sortKey: '2026-08-14T14:00:00Z',
  title: 'A player’s match count dropped a few games under the Junior filter, even with no Juniors involved',
  items: [
    'A player profile’s "matches" total (and its bowling/fielding twins) counted only games with a batting innings, a bowling spell or a fielding entry once a grade-category filter was active: so a game where the player only did one of the three, or was named but never got a bat, silently dropped off the count. It read as though the Junior filter had wrongly swept up a non-Junior game.',
    'Fixed to count every game the player appeared in at all: batted (including a did-not-bat entry), bowled, fielded or was simply on the card. Matching how the season-by-season table underneath it was already counted. The header now reconciles with that table again.',
  ],
}
