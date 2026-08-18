export default {
  version: 'v9.30.0',
  date: '2026-08-18',
  sortKey: '2026-08-26T14:00:00Z',
  title: 'Outbound email kill switch, paused by default',
  items: [
    'The emails BetterCricket sends on its own are now held. Nine automated ones (six trial nudges, qualification expiry, fees owing, Club Diary task due) and seven transactional ones (invites, both password resets, the signup verification code, the member portal sign-in link, vote nudges, unpause requests) stop the moment this deploys — no switch to find first.',
    'Club newsletters sent from BetterComms, its test send, and sales rep emails are never affected. They keep working exactly as before.',
    'Two switches in All Clubs → General Settings turn each group back on independently. Both start paused, and a settings row that cannot be read stays paused rather than letting email out.',
    'While transactional email is paused, nobody can accept an invite, reset a password, finish a self-serve signup, or sign in to a member portal. The switch says so.',
    'Every message now carries what kind of send it is, and anything that does not name one is held rather than slipping out. The three daily scans skip entirely while paused instead of running and failing.',
  ],
}
