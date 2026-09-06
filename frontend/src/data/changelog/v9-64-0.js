export default {
  version: 'v9.64.0',
  date: '2026-09-07',
  sortKey: '2026-09-08T10:00:00Z',
  title: 'Every panel now says which filter it is under',
  items: [
    'The filter bar sits above every tab on a player profile, but it only ever reached some of them. Each panel it does not reach now says so, in its own words, instead of leaving you to work out whether a number is filtered.',
    'Matches by grade on Analysis, Team now follows the filter like the rest. Filter to Men\'s and the junior grades leave the grid, the way they already left Runs by grade on the Batting tab.',
    'Picking a match type is the exception, and the grid says why: a format is recorded on each fixture, and Cricket Australia\'s own per-grade figures carry none, so under Two Day, One Day or T20 the grid is what we hold a scorecard for and nothing more.',
    'Competitions and Formats list every value on purpose, so filtering them would leave a single row. They now say that rather than looking broken.',
    'Milestones and Honours are counted across a whole career whatever is filtered, because a milestone is not a men\'s milestone. They say so.',
    'The career note no longer describes itself as the figure above it. A club with junior grades already has a filter on by default, so the headline is often neither career number, and the note now names both sources instead of claiming to be one of them.',
    'Nothing is shown on any of this while every filter is set to All.',
  ],
}
