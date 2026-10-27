export default {
  version: 'v9.132.6',
  date: '2026-10-27',
  // Above v9.132.5's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-09T22:00:00Z',
  title: 'Player Dashboard: switch it on from BetterStats',
  items: [
    'New: BetterStats > Records & content > Player Dashboard. Turn the player page on or off, choose whether it needs the last-4 PIN, show or hide the Player Dashboard button on your club site, pick which sections players see and in what order, and copy the link or QR code. None of it needs BetterSelect.',
    'Fixed: a club without BetterSelect had no screen for any of this, because the controls only existed inside BetterSelect. The page itself already worked, so existing links keep working and a club that has not touched the new switch stays as it was.',
    'For a club with BetterSelect, availability and votes keep their own switch in BetterSelect > Availability. The two switches do not affect each other: the dashboard can be on with availability off, or the other way round. Until a club chooses, the dashboard follows the availability switch as it always did.',
    'Hiding the club site button now leaves the link working for a club without BetterSelect, the same as it does for one with it.',
  ],
}
