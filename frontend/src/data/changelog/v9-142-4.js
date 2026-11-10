export default {
  version: 'v9.142.4',
  date: '2026-11-10',
  // Above v9.142.3.2's sortKey (2026-11-19T09:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T10:00:00Z',
  title: 'A game against another BetterCricket club now counts everywhere',
  items: [
    "A game between two clubs that both use BetterCricket is stored once, under whichever club synced it first. Several screens only looked under your own club's season, so your half of those games went missing as soon as you picked a season. This release fixes the ones we found.",
    "StatLab: picking a season (one or several) now keeps those games in every table and record. A player's season is one row again instead of one row per club's copy of the season.",
    "The Club tab on Records now includes them when a season is picked.",
    "The Games list in the admin now shows both of your fixtures, with and without a season, and counts only your own players as named in a called-off game.",
    "Upload Scorecard now warns when the match you are uploading is already in your data under the other club's copy, so it is not counted twice.",
    "The public Lineups page lists those games under past games when a season or grade is picked.",
    "BetterIQ: a player's deep dive and the selection season load count them when a season is filtered.",
    "Some other screens still read only your own club's season. They are listed in a new check, audit_game_ownership_reads.py, which now fails when a new screen is added that does the same.",
  ],
}
