export default {
  version: 'v9.119.0',
  date: '2026-10-19',
  sortKey: '2026-10-19T01:00:00Z',
  title: 'Settings holds the pool controls, team default filters, and the Filters panel is fixed',
  items: [
    'The Filters panel on the Selection board no longer breaks the page. It used to open inside the pool card and push the player list out over the card\'s edge. It now floats over the list, stays inside the window, scrolls inside itself when the window is short, and closes on Escape or a click outside.',
    'The "Played within" dropdown and the "Show juniors" switch are gone from the Selection board, Whiteboard, Availability, Fixtures and Selection overview. They live in BetterSelect, Setup, Settings now. Junior grades are a Show or Hide choice there (remembered on this device).',
    'New in Settings, Players listed: how far back a player\'s last game may be for the pool to list them, separately for the Selection board and Whiteboard (any time, this season, or 1 to 10 years) and for Availability (any time, or 1 to 10 years). Typing a name in search still finds anyone, whatever the window.',
    'New in Settings, Team defaults: write what each team\'s Selection board starts on as rules. Pick the teams, then any of: a gender (the women\'s team starts on Gender = Women), the squads shown (all, the top N by XI number, or chosen squads, so the 1st XI only sees the top two or three), and a played-within window for that team.',
    'A team\'s default shows as a line at the top of the pool ("Team default: Women · 1st XI, 2nd XI"). Your own filters win over it, and "Show everyone" turns it off for that match. It never removes anyone for good, and a team with no rule starts on everyone as before.',
    'The Availability screen is shorter: the two controls are off it, and the Current squad / All switch stays.',
  ],
}
