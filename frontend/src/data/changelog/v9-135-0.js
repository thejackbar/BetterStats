export default {
  version: 'v9.135.0',
  date: '2026-10-29',
  // Above v9.134.5.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-12T10:00:00Z',
  title: 'Captain and wicketkeeper on hand-entered and imported matches',
  items: [
    'New: Match Info on the Manual Games form and the Details button on every manual and imported match now have a Captain and a Wicketkeeper. Pick from the players on the card, or search for anyone in the club. A match can have two wicketkeepers if the gloves changed hands.',
    'New: is_captain and is_wicketkeeper columns in the spreadsheet import. On a match you are overwriting, blank cells keep the captain and wicketkeeper it already had. The import page says how many matches named each.',
    'New: when the captain of a grand final the club won is set, their premiership honour carries the Captain detail, the same as on a Cricket Australia match.',
    'Changed: the Cricket Statistics for Windows converter reads the captain and wicketkeeper flags out of the club\'s files. The wicketkeeper flag checks out against every stumping and keeper catch in the Shoalwater Bay archive. The captain flag is one player per match in 894 of 918 matches, so check it against your scorebook.',
    'New: a script adds the captain and wicketkeeper to matches that are already imported, so a club does not need to import its scorecards again. It finds each match by date, opposition and grade, finds each player among the players on that match\'s card, never overwrites a role the club has set, lists what it could not place, and can be undone as a whole.',
  ],
}
