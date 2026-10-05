export default {
  version: 'v9.106.16',
  date: '2026-10-05',
  sortKey: '2026-10-05T23:00:00Z',
  title: 'Fantasy: players Cricket Australia lists under a new id now score',
  items: [
    'Some players are on the team sheet under an id we never stored for them. Cricket Australia can issue a new one for a new registration, and a player new to the club who was added by hand has none. Sync dropped their whole game, so they showed on the scorecard and scored nothing in Fantasy. This is what happened to David Gardner and Ashton Taylor at Scarborough.',
    'Sync now recognises a player on the team sheet by their full name when exactly one player at your club has that name, and stores their appearance, batting, bowling and fielding on that player. A name two players share, or a short name like "D Gardner", is never matched.',
    'Games already stored are fixed with a script that adds the missing rows and nothing else: python -m app.scripts.relink_rostered_players <club> lists who it would attach to which profile, and --apply adds the rows and settles any Fantasy round whose points moved.',
    'The match scorecard linked a row to the wrong profile when two players shared a surname and first initial: Ashton Taylor\'s runs showed against Angus Taylor. It now uses the full name from the team sheet first, and links on surname and initial only when one player fits and the first names agree.',
  ],
}
