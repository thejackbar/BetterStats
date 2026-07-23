export default {
  version: 'v8.78.0',
  date: '2026-07-23',
  sortKey: '2026-07-23T09:00:00Z',
  title: 'Match scorecard: fixed a wrong innings total and a duplicated bowling spell',
  items: [
    'A match scorecard could show a wrong innings score and wicket count when a player already registered with the club had turned out for the OTHER team that day. Their innings was being pulled onto the wrong side of the card, which also stopped the real Grassroots total from being used. Reported case: an opponent\'s innings showed 30/1 on the card header while the batting list below it showed seven dismissals, when the real score was 135/7.',
    'A bowler could occasionally show up twice on a scorecard with the same figures, once correctly and once as a bogus "FILL-IN" entry with a CLAIM button. Grassroots was reporting a different participant id for the same real bowler than the one already on file. Bowling and batting rows are now matched to a player by name as a fallback when the ids don\'t line up, the same way the rest of the scorecard already does.',
    'Under the hood, the scorecard endpoint now always builds both teams\' batting, bowling and innings totals directly from Grassroots\' own match data when it\'s reachable, which covers essentially every synced game. Our own player records are used only to attach a profile link to a name, not to decide which team a row belongs to or what its numbers are. Our stored data is still used as a fallback if Grassroots can\'t be reached for that request.',
  ],
}
