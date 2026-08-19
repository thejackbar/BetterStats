export default {
  version: 'v9.32.1',
  date: '2026-08-19',
  sortKey: '2026-08-31T09:00:00Z',
  title: 'A washed-out game no longer counts as a match played',
  items: [
    'PlayHQ counts a player as having played the moment they are named in the side, even if the game was then abandoned or cancelled. So a club that picked a team for three rained-off Saturdays saw those three on every one of those players\' records. They no longer count. Reported by a club whose season is 14 fixtures, where three washouts is most of the difference between our figure and their own.',
    'A game abandoned after play started still counts. If someone batted, bowled or took a catch, they played, and the club counts it, so we do too. Only a fixture nobody got onto the field for comes off.',
    'The club\'s Matches screen lists the fixtures that were called off, and how many players were named in each, so the correction is visible rather than a number that quietly disagrees with PlayHQ. Called-off games read ABANDONED on the public results list instead of leaving the result column blank.',
    'Current-season figures correct themselves on the next sync, with no rebuild. Earlier seasons need a one-off pass from the server, which we will run for the clubs it affects. About 45 clubs have at least one of these; for most it is a game or two across a long season, and 57 clubs have none at all.',
  ],
}
