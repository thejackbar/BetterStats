export default {
  version: 'v9.110.10',
  date: '2026-10-13',
  sortKey: '2026-10-13T12:00:00Z',
  title: 'Clubs with an ended trial can ask for an extension from /trial',
  items: [
    'On /trial, picking a club that is already registered but whose page is paused used to land on a "Club page paused" screen with nowhere to go. It now opens a Request trial extension form instead.',
    'The form asks for a name, email, phone number, role at the club and a short message about why they want more time. All five are required. The request is emailed to Jack and Elton, with the sender as the reply-to address, and is also saved in the Onboarding list as a trial_extension_request.',
    'If the email cannot be sent, the person sees a plain message with the support address rather than a thank-you. Clubs with a live page still open it, and clubs not yet registered still get the set-up choice.',
  ],
}
