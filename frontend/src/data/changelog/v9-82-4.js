export default {
  version: 'v9.82.4',
  date: '2026-09-18',
  // Above v9.82.3's sortKey (the highest on origin/main). Check origin/main at
  // merge time.
  sortKey: '2026-09-28T20:00:00Z',
  title: 'Open shifts on the roster no longer read "undefined"',
  items: [
    'On BetterAdmin → Roster (People view), open-shift chips could show "undefined ×2" as their description. That happened when a shift belonged to an operational area that had since been archived — the chip was naming the shift by looking its area up in the active-areas list, which no longer held it. A shift now carries its own area name, so it reads its real area whether or not the area is still active.',
    'The same open-shifts row also merged two different roles at the same time in one area into a single chip (hiding one role). Now that a shift is for one role, each role shows as its own chip with its own count — an Umpire pair reads "×2" beside a separate Scorer chip, rather than one "×3" that swallowed the Scorer.',
  ],
}
