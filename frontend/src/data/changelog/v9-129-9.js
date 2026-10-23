export default {
  version: 'v9.129.9',
  date: '2026-10-23',
  // Above v9.129.8's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T23:30:00Z',
  title: 'BetterFantasy: rounds now lock one hour before the first match',
  items: [
    'A Fantasy round used to lock at 9am on its first game day, Melbourne time, for every club. It now locks one hour before the first match of the round starts, in the club\'s own timezone. For Applecross, round 1 on Saturday 24 October locks at 11am AWST.',
    'The start time comes from the Play-Cricket draw, so it follows a match that moves. If a round\'s first day has several matches, the earliest one counts. If the draw gives no time for that day, the lock falls back to 9am local.',
    'The timezone comes from the club\'s state (WA uses Perth time, SA Adelaide time, and so on). A time you set by hand on a round still wins, and a scored round is left alone. "Use the default" now goes back to the hour before the first match.',
  ],
}
