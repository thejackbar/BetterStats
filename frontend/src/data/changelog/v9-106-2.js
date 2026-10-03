export default {
  version: 'v9.106.2',
  date: '2026-10-03',
  sortKey: '2026-10-03T23:00:00Z',
  title: 'Merging players keeps their photo and details; Players page shows everyone',
  items: [
    'Merging two players now keeps the person, not only their cricket. The photos, email, phone, date of birth, shirt number, squad, batting and bowling style, availability, squad and lineup spots, nets attendance, family links and club member record all move to the player you keep. Before, only the games moved and the rest went with the record you removed.',
    'Where both players already have the same thing, the player you keep wins. A photo is only filled in when the kept player has none, and a member record is never deleted to settle a clash.',
    'Undoing a merge hands the squad, availability, lineup and member record back to the restored player. A photo or detail that was filled in stays with the kept player.',
    'The Players page no longer shows a row of dashes for someone under your club\'s minimum-innings setting. That setting is for ranking strike rates on the leaderboard, so the roster now ignores it.',
    'M on the Players page now counts a bowler who never batted. It uses whichever of the batting and bowling figures has the player.',
  ],
}
