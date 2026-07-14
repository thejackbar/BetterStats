export default {
  version: 'v8.61.0',
  date: '2026-07-14',
  sortKey: '2026-07-14T18:00:00Z',
  title: 'A club can now choose whether fill-ins show in partnerships and fielding, and can promote one to a real player',
  items: [
    'A fill-in\'s runs and wickets have always shown on the batting/bowling card. Partnerships and fielding are a separate, lower-stakes call, so a new Settings toggle ("Show fill-ins in partnerships & fielding", on by default) lets a club leave those two cards to registered players only if they\'d rather. It never touches all-time club records either way.',
    'A club admin with player-management access can now click CLAIM on a fill-in row to promote them into a real player: edit the name, optionally match them to an existing player if it turns out to be someone already registered under a different scorecard identity, and leave an optional reference note for the club\'s own records.',
    'Pasting a Cricket Australia/PlayHQ profile link is not auto-verified — their player pages don\'t offer a public lookup we can call, so a pasted link is stored as a plain note rather than something we silently pretend to resolve.',
  ],
}
