export default {
  version: 'v9.106.28',
  date: '2026-10-05',
  sortKey: '2026-10-05T22:00:00Z',
  title: 'New players are now picked up and merged automatically when they play their first game',
  items: [
    'A player who was new to the club when their first game synced used to be left out of that game for good, so they had no appearance, no stats and no match fee for it. Every sync now checks the games it reads and adds anyone the team sheet names whom the club holds. It uses the scorecard it already has, so there are no extra requests to Cricket Australia.',
    'A player added by hand (in the roster, Directory, Fees, nets, BetterSelect or Fantasy) is now merged into their real record once they play, if it is clear they are the same person: the same full name, nobody else at the club with it, no cricket of their own on the hand-added record, and the real record is new this season. Squads, availability, fee lines, family links and Fantasy picks move across, Fantasy points are scored again, and the merge is in the merge log where it can be undone.',
    'Anything less clear is left on the merge screen as before: two people with one name, a player who has played in earlier seasons, a record the club kept apart, a player with a login, or an imported record.',
    'A hand-added player the sync matches to a team sheet by full name now takes that player\'s Cricket Australia id, so the season totals find the same record instead of creating a second one.',
  ],
}
