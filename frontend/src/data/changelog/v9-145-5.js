export default {
  version: 'v9.145.5',
  date: '2026-11-18',
  // Above v9.145.4's sortKey (2026-11-21T12:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-21T13:00:00Z',
  title: 'Choose how far ahead players can give their availability',
  items: [
    'You can now set how many weeks ahead players can answer on their own page. There are two settings: one for saying Available (or Maybe) and one for saying Unavailable. For example, players can say Available for the next 4 weeks and Unavailable up to 8 weeks out, so holidays get flagged early.',
    'Find the settings in BetterSelect, Availability, under Self-service link. Both start at No limit, so nothing changes until you pick a number.',
    'On the player page, answers outside the limit are greyed out and the card says the date they open. For a two-day game, the quick answers that would break a limit are greyed too.',
    'Selectors can still record any answer for any date, and answers already given stay as they are.',
  ],
}
