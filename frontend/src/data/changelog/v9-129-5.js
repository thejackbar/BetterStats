export default {
  version: 'v9.129.5',
  date: '2026-10-23',
  // Above v9.129.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T20:00:00Z',
  title: 'Player dashboard: selected shows in the date header, and a tidier Selection and Stats',
  items: [
    'When you are selected in a side, the date it is on says so in its header: a green chip with the team (for example "✓ 3rd XI") and one line under the day with the time, the opponent and Captain or Keeper if that is you. A two-day game shows it on both dates. Open the games and the one you are picked in is tagged Selected and listed first.',
    'The two-day "which weeks?" card is now one short row: Both, W1 only, W2 only, Neither, with a one-line status and a small "Maybe for both" link. It no longer lists every team in the game.',
    'Squad, Selected and Training are one "At a glance" block of short rows instead of three cards. Your squad is not repeated there, because it is already under your name at the top.',
    'Stats are flatter and shorter. Each discipline is a label and a clean row of figures with no box around every number, fielding is one line, and your last innings and spells sit under a thin "Form" and "Spells" heading. The footnote is two short sentences.',
  ],
}
