export default {
  version: 'v8.62.1',
  date: '2026-07-14',
  sortKey: '2026-07-14T20:30:00Z',
  title: 'Fixed matches-played showing zero for some clubs',
  items: [
    'A club’s season stats (runs, wickets, players) come from CA’s participant data, but matches played, win/loss record and the results list were worked out by matching the club’s name against the free-text team names CA sends back. A club whose CA-recorded team text didn’t exactly contain the first word of its name (a hyphenated name spelled differently, for example) showed zero matches played despite having a full season of synced data. That matching is now based on which players actually appear in each game, the same reliable link the rest of the stats already use.',
  ],
}
