export default {
  version: 'v9.110.9.2',
  date: '2026-10-13',
  sortKey: '2026-10-13T10:00:00Z',
  title: 'Password reset emails now say when they did not go',
  items: [
    'Email reset link on the Users page used to say it had sent the email even when the server had no way to send it. It now sends the email before answering, and shows a plain message if nothing was delivered.',
    'Super Users has a new Email reset link button. Reset password there sets a password you type and has never emailed anyone; the panel now says so.',
  ],
}
