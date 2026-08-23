export default {
  version: 'v9.51.4',
  date: '2026-08-22',
  sortKey: '2026-08-23T08:00:00Z',
  title: 'Fixed: a sales email could report itself sent when nothing had been sent',
  items: [
    'When no email provider is connected, BetterCricket falls back to a stand-in that writes the email to the log instead of sending it. That stand-in was reporting success, so the Sales Workspace recorded the email as sent, told the rep it had gone, and the club never received it.',
    'A send now refuses outright when no provider is connected, and says so: “No email provider is connected, so nothing was sent.” A trial extension still goes through, and the confirmation says plainly that the email did not, so the club can be told another way.',
    'The email panel in the club drawer warns before you write anything if sending is not connected, the way the Comms screens already did.',
    'Every sent email now records which provider took it and the id it was given, so “did that actually go?” has an answer later.',
  ],
}
