export default {
  version: 'v9.123.4',
  date: '2026-10-19',
  // Above v9.123.3.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-26T09:00:00Z',
  title: 'Availability: a shorter Squad filter and a "Hasn\'t played" filter',
  items: [
    'The Squad filter on Availability used to list every squad and grade name the club has ever had. It now lists only squads someone in the shown list belongs to, drops squads switched off in Teams, and leaves out junior squads unless Show juniors is on in Settings.',
    'New "Hasn\'t played" dropdown next to Current squad and All. It keeps players whose last game was more than 1, 2, 3, 5 or 10 years ago, so you can find the lapsed ones.',
    'It only offers choices that can find someone. On Current squad the list already stops at your dormancy window, so you get "more than 1 yr"; switch to All to look further back. Players with no game on record are left out.',
  ],
}
