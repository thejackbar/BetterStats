export default {
  version: 'v9.42.5',
  date: '2026-08-21',
  sortKey: '2026-08-22T00:30:00Z',
  title: 'B&F votes on a player page',
  items: [
    'A player page now has Club B&F votes and Competition B&F votes beside Games, Goals and BOG, so the season by season table breaks a vote tally down by grade and by year the same way it does everything else.',
    'A season shows its own vote total, which can be more than its grade columns add up to: votes on a sheet that never named a grade have no column to sit in, and they still count.',
    'Votes come straight from what was imported, so a season that has since been synced from PlayHQ keeps the votes recorded against it rather than losing them to the newer figures.',
    'The tabs only appear where there is something to show: a player with no votes recorded does not get them, and neither does a club that has switched that board off in Settings.',
  ],
}
