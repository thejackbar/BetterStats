export default {
  version: 'v9.120.0',
  date: '2026-10-19',
  // Above v9.119.0.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-19T06:00:00Z',
  title: 'A dashboard for each player, and Fines in BetterSelect',
  items: [
    'The My page tab a player opens with the last 4 digits of their mobile is now a small dashboard. Your club picks what goes on it and in what order, in Availability under Self-service link, Player page. New modules: the ladder for the player\'s squad, fees owing, and a short season overview (matches, runs, high score, batting average, wickets, catches).',
    'Fees owing only shows when the club has the BetterAdmin fees module and the PIN is on. With the PIN off, anyone with the link could open anyone\'s page, so the fees module is held back and the setting says why.',
    'New Fines screen under BetterSelect, Club Life. Switch it on for a squad, then after a game enter the session: pick the date, then a line per fine from your own fine list (name and price) or typed in as a one-off. A tracker shows each player\'s fines week by week, what they have paid into the pot and what they still owe.',
    'Record a payment with Paid (it fills in what the player owes). History shows every fine and payment for a player, and Void takes a mistake out of the balance without deleting it. You can bring it back with Restore.',
    'Set up how players pay once per squad: PayID, bank transfer details, a reference and any extra note. Players see their balance, the week-by-week list and those details, each with a Copy button, in a Fines section on their page. A squad with Fines off shows nothing.',
  ],
}
