export default {
  version: 'v8.37.3',
  date: '2026-06-27',
  sortKey: '2026-06-27T03:00:00Z',
  title: 'Send a test email, plus an SES status panel for staff',
  items: [
    'Comms Settings now has a "Send a test email" box, so a club admin can check the setup by sending a test to any address using the current sender settings.',
    'A no-reply option sits next to the reply-to field for emails you do not want replies to.',
    'Better staff see a read-only Amazon SES status panel: which provider is live, the region, the verified sending domains, the configuration sets and webhook settings. AWS credentials are never shown here; they stay in server config.',
  ],
}
