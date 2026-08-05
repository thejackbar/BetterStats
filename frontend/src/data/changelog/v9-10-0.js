export default {
  version: 'v9.10.0',
  date: '2026-08-05',
  sortKey: '2026-08-08T15:00:00Z',
  title: 'Confirm the roster, freeze the first column, and drag shifts the way you expect',
  items: [
    'A new Confirm tab closes off the week. It lists every shift someone was rostered to, with the hours already filled in from the shift length, so you only touch the ones that were different. Confirming records those hours against each volunteer, split paid and volunteer.',
    'Set someone to zero hours if they did not turn up. Confirming a corrected week updates what was already recorded rather than adding a second copy, and reopening a confirmed week leaves the recorded hours alone.',
    'The first column stays put while you scroll across the days, so a shift is never separated from the name it belongs to.',
    'Both the first column and the volunteer pool can be minimised, and each remembers what you chose the next time you open the roster. The setting is yours, not the club\'s.',
    'Fixed: dragging an available, qualified volunteer from the pool onto an open shift did nothing at all in the People view, with no message to say why. It now rosters them, and says so.',
    'A shift can be dragged onto a different volunteer on the same day. Other days are not drop targets, since a shift belongs to its day, and a volunteer who cannot take it shows as blocked before you let go.',
    'Every rostered shift now carries a small cross to hand it back to the open pile, without hunting for it in the sidebar first.',
  ],
}
