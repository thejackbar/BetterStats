export default {
  version: 'v8.94.5',
  date: '2026-07-30',
  sortKey: '2026-07-30T09:00:00Z',
  title: 'Votes: fixed a bug hiding the team list, plus filters for the Fixtures tab',
  items: [
    'Fixed a bug where a played fixture could show "0" for every team-list source on the Votes page — Match scorecard, BetterSelect XI and Play.Cricket team list — even when a team list and a full scorecard genuinely existed. A behind-the-scenes id mismatch meant the vote page was checking the wrong match.',
    'The Fixtures tab on the Votes page now has Team/Grade and Round filters plus an opponent search, instead of one long list of every fixture in the season.',
  ],
}
