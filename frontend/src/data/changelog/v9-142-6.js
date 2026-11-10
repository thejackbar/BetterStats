export default {
  version: 'v9.142.6',
  date: '2026-11-10',
  // Above v9.142.5's sortKey (2026-11-19T11:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T12:00:00Z',
  title: 'Returning clubs: an earlier admin can register again, and we are told every time',
  items: [
    'An earlier admin of a club whose trial ended can now register again with their own email. Before, the sign-up stopped them with "This email already belongs to a BetterCricket account". It now says welcome back, asks for no password, and restarts the club\'s trial.',
    'Their login is left exactly as it is: password, username and profile are not changed, and no second account is made. They are not signed in by the form either. They get a "sign in" button and use the password they already have, or "Forgot your password?" on the sign-in page.',
    'Only that case is let through. An email on any other account, an admin of a different club, an admin of a club that is still on a live trial, and a member who is not an admin are all still refused. The email code and the Terms tick are still needed.',
    'When a club whose trial ended registers again, Jack and Elton get an email straight away and the same text is saved as a note on the club\'s deal. Every returning club is flagged for a personal follow-up.',
    'The email says who registered (name, email, phone), whether it is a new person or the club\'s own admin coming back, which earlier admins still have access, when the club first registered and when its trial ended, and how they found us.',
    'It also lists what happened in the 24 hours before they registered: their own visits, searches for the club and picks of it on the trial page, views of the club\'s pages, what its earlier admins did, our emails they opened, contact forms, and any calls or notes from our side. A part that could not be read says so instead of showing as empty.',
    'On the deal, a new person becomes the contact to ring. The earlier contact stays linked. If no live email provider is set up, the email is not sent and the note on the deal says so.',
  ],
}
