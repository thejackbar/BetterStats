export default {
  version: 'v9.24.2',
  date: '2026-08-15',
  sortKey: '2026-08-17T18:00:00Z',
  title: 'Sales Workspace. Email actions with tracked links',
  items: [
    'The Workspace drawer can now send an email straight to a contact: three built-in templates (general information, trial steps, book a demo) plus a custom subject/body, without leaving the call screen.',
    'Every link in a sales email carries UTM tags (source, medium, campaign and the sending rep\'s own username), plus the club\'s own tracking code, so a later site visit or trial signup can be traced back to both the club and which rep sent it.',
    'Sending is blocked server-side for a contact marked Do Not Contact or already opted out of email: the same rule the drawer\'s badge already shows, enforced again on the actual send so a stale screen can\'t get around it.',
    '"Book a demo" links out to the sending rep\'s own booking page when one is on file (Super Admin → All Clubs → General Settings → Sales demo booking links); with none configured it asks the contact to reply and arrange a time instead of sending a dead link.',
  ],
}
