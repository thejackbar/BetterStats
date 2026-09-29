export default {
  version: 'v9.97.2',
  date: '2026-09-29',
  sortKey: '2026-10-04T12:00:00Z',
  title: 'Importing stats matches "Steve" to your "Steven"',
  items: [
    'When an imported sheet names a player by a short form of a first name the club already holds ("Salter, Steve" for "Salter, Steven", "Chris" for "Christopher"), the scorecard import and Import Stats now pre-select that player and say why. Previously each one was offered as something to check, and "Create all as new players" turned them into a second record holding half a career.',
    'A suggestion is only made when exactly one of your players fits and the sheet does not also name the full form. Where both careers are known and are more than five years apart, the player is offered but not pre-selected, because that is often a father and son.',
    'A nickname that is not the start of the full name (Bob for Robert) is still left for you to match by hand.',
    '"Create all as new players" no longer touches a suggested match. You can still change any of them before importing.',
  ],
}
