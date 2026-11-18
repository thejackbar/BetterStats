export default {
  version: 'v9.145.3',
  date: '2026-11-18',
  // Above v9.145.2's sortKey (2026-11-21T10:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-21T11:00:00Z',
  title: 'Juniors off the selection pool, bulk inactive, and an opener who retires',
  items: [
    'Admin, Players: tick players, or Select all shown, then Mark inactive or Mark active in one go. A new "Not played in N years" filter finds your past players to tick.',
    'Marking players inactive in bulk takes them out of every squad, the same as doing it one at a time, and is recorded on the audit trail.',
    'Selection board and Whiteboard: players whose squads are all junior sides (Year 4, Under 13 and so on) are left out of the pool unless juniors are shown. A Show juniors box sits by the pool, and typing a name still finds a junior who is filling in.',
    'Fall of wickets editor: a retirement before the first wicket now works when Cricket Australia lists the batter twice (retired, then out later). The editor moves the first row into the retirements for you.',
    'Wickets down on a new retirement starts at 0.',
    'Sponsors: the player card box now explains that a card carries one sponsor, and the two choices are for the share card and the Player Cards.',
  ],
}
