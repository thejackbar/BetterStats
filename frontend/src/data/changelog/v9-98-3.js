export default {
  version: 'v9.98.3',
  date: '2026-10-05',
  // Above v9.98.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-05T09:00:00Z',
  title: 'Trials: BetterStats can be trialled again after a Reset, and add-ons wait for it',
  items: [
    'All Clubs > after you Reset BetterStats for a club, the "+ BetterStats" button now works. It was locked, so a reset club had no way to start a new BetterStats trial from that screen.',
    'A module can only be trialled while BetterStats is live. Every add-on switches off when BetterStats lapses, so a trial started then did nothing and still used up the club’s one trial of that module. The trial is now held back, and the club’s Dashboard and Account page say to start or restore BetterStats first.',
    'The same rule applies when a Super Admin starts an add-on trial or approves a trial request. They get a message naming the fix instead of a trial that does nothing.',
  ],
}
