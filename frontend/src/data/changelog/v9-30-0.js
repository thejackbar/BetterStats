export default {
  version: 'v9.30.0',
  date: '2026-08-18',
  sortKey: '2026-08-26T09:00:00Z',
  title: 'Competitions, player search and re-graded teams (BetterFootball)',
  items: [
    'Rounds a team played before being re-graded mid-season now sync. PlayHQ only ever reports the division a side is in right now, so a team promoted or relegated after a few rounds was silently missing the ones it played first. The sync reads each team\'s own fixture as well, which is the only place the earlier division shows up.',
    'Settings now takes the competitions your club has played in, alongside your former names, and they show beside the season picker on your club page. Only the seasons PlayHQ ran are synced, so a league you left before that is yours to add.',
    'Every page has a player search in the menu bar, matching BetterCricket. Type a name and go straight to the profile.',
    'Merge Players can now split a record in two, for when one record is really two people with the same name. Tick the seasons that belong to the second person and they move to a new record. Merging them back is the undo.',
    'Fixed: merging two players kept only their synced games. Imported seasons and honour-board entries were left behind and dropped out of every total. They move across with the rest now, and come back if the merge is undone.',
  ],
}
