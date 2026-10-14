export default {
  version: 'v9.111.0',
  date: '2026-10-14',
  sortKey: '2026-10-14T09:00:00Z',
  title: 'Email the confirmed side, and fixes for clubs that share a first word',
  items: [
    'New: the Email button on the Selection board sends the confirmed side to the captain as a team sheet in batting order, with each player\'s mobile from their profile. It also emails each selected player the match details and who their captain is. Players under 18 are not emailed directly, and anyone without an address is listed so you can follow up.',
    'New: a setting in Selection rules to email the captain automatically when a side is confirmed. It is off until you turn it on, and it will not send the same side twice.',
    'Fixed: a club that shares your first word, such as North Beach for North Perth, no longer has its fixtures, results or ladder row mixed in with yours. Your teams are now recognised by the club that owns them, with the name used only when Cricket Australia gives no club.',
    'Fixed: an away game against a club with a similar name was filed as a home game with your own club as the opponent. A team with a sponsor\'s name and none of yours was dropped from Fixtures. Both now show correctly.',
    'Fixed: opening a match from your club\'s pages when the other club\'s sync loaded it first showed their result and their club\'s colours and website. The page now reads the game from your side, so a win shows as a win.',
    'Fixed: a game the other club loaded first could be left out of your stats when your team name was spelled slightly differently in two places on the scorecard. The side is now matched on the team itself. Run Sync Now to correct games already loaded.',
    'Fixed: Selection listed squads you never made, taken from every team name that had ever been on a scorecard, and counted squads you had switched off. It now lists only your live squads, with each player\'s top squad first.',
  ],
}
