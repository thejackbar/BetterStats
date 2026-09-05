export default {
  version: 'v9.66.0',
  date: '2026-09-05',
  sortKey: '2026-09-12T10:00:00Z',
  title: 'A retired not out is not a dismissal',
  items: [
    'Batting averages worked out from scorecards were counting a "retired not out" as a wicket, so a filtered figure on a profile, a leaderboard or StatLab could sit below the same player\'s figure on PlayCricket. It counts as a not out now, the way the Laws and Cricket Australia both have it.',
    'Retired hurt is treated the same way. A "retired out", where a batter retires without the opposing captain\'s consent, is still a dismissal, because under the Laws it is one.',
    'Every average across the app now divides by the same thing: innings less not outs. Two panels, batting by opposition and batting by venue, had been leaving an innings whose dismissal was never recorded out of that sum, so a player could read two averages on one profile.',
    'Retiring not out no longer counts as a duck, and it no longer shows on the record book\'s list of unusual dismissals, since it is not a way of getting out.',
    'Uploading a scorecard now offers retired not out, retired hurt and retired out separately, so the card can say which one it said.',
    'Figures already stored are corrected by a one-off run over each club, so a club does not need to re-sync its history.',
  ],
}
