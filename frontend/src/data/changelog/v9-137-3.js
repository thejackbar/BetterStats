export default {
  version: 'v9.137.3',
  date: '2026-11-01',
  // Above v9.137.2.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T00:00:00Z',
  title: 'Player page names, and match stats on the ballot',
  items: [
    'Fixed: a player\'s own page, the vote pages and net check-in printed names as "Barendse, Jack" whatever the club had picked under Settings. They now follow the club\'s player name format, so a club on First Name Last Name sees "Jack Barendse" in the header, the signed in line, the name pickers and the ballot.',
    'Fixed: the vote page thanked a player by their surname ("Thanks, Barendse"). It now says "Thanks, Jack".',
    'New: each player on the voting ballot has a small line under their name with what they did in that game, for example "45* (32) · 2/18 (4 ov) · 2 ct" for runs (a star if not out) and balls, wickets and runs against with overs, and catches, stumpings and run outs. A player who took the field but did not bat or bowl reads "Did not bat or bowl". Games that are not scored yet show no lines, and a player who is hidden from the public pages shows no line.',
    'New: the same line sits under each name in the votes a player has already cast on their own page.',
  ],
}
