export default {
  version: 'v9.30.0',
  date: '2026-08-18',
  sortKey: '2026-08-26T14:00:00Z',
  title: 'Reminder and nudge emails can be paused',
  items: [
    'The nine emails BetterCricket sends on a timer with nobody asking for them — six trial nudges, qualification expiry, fees owing, Club Diary task due — are now paused, and stay paused until switched on in All Clubs → General Settings.',
    'Nothing that carries a system operation can be paused. Invites, both password resets, the signup verification code, the member portal sign-in link, vote nudges and unpause requests always send. There is no setting for them, and no configuration, missing settings row or database failure can hold one back.',
    'Club newsletters sent from BetterComms, its test send, and sales rep emails always send too.',
    'Every message now records what kind of send it is, and only the reminder kind is pausable at all. The three daily scans skip entirely while paused instead of running and failing.',
  ],
}
