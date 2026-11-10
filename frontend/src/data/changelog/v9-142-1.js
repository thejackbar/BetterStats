export default {
  version: 'v9.142.1',
  date: '2026-11-09',
  // Above v9.142.0's sortKey (2026-11-19T04:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T05:00:00Z',
  title: 'Nets by time slot: check in from your own page, see where you bat, change times, print',
  items: [
    'Players can check themselves in to tonight\'s nets from their own page. Once they are in, the page shows their net and the time they bat (and second go times), or their place in the batting order for a queue session. It updates when the coach moves someone. The Selection heading on the page says where you bat.',
    'Page check-in closes when the first slot starts and fills the grid ahead of time. The QR code and the coach still check latecomers in, and they take the next slot that has not started.',
    'The top of a time-slot session now shows who is in now, who is next, and a timer for the running slot. Rows are shaded for in now, pad up and next, each with a word on it. A pad up alarm sounds before every change (2 minutes by default, set in Edit nets, 0 turns it off), and a change over alarm sounds when the slot ends.',
    'Click a time on the left of the grid to change it. The slot above runs longer or shorter and every later time moves with it, so fewer players than expected means longer early turns. People keep their slots. A changed slot is underlined.',
    'A Print button opens a one-page sheet (landscape for the grid, a plain list for the queue).',
    'A session can be switched between Batting queue and Time slots from the session screen. Nothing is deleted either way.',
  ],
}
