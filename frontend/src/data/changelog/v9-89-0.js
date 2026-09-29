export default {
  version: 'v9.89.0',
  date: '2026-09-29',
  sortKey: '2026-09-29T02:30:00Z',
  title: 'Certificate reminders that follow through, grade milestones, and a test email',
  items: [
    'A lapsing certificate now gets up to three notices: when it enters the notice period, a final reminder close to the date (14 days by default, set per club, or off), and the day it lapses. Before this a certificate was mentioned once and never again, lapse included.',
    'A lapsed certificate is marked urgent, and lapsed ones are listed first.',
    'Certificates are no longer chased once renewed (a newer record of the same type for the same person), when the person has been archived from the Directory, or when the certificate type has been retired.',
    'Certificates that lapsed long ago are left out (90 days by default, set per club), so switching this on no longer buries this week\'s renewals under ones from years ago.',
    'New notifications for grade milestones, such as 50 matches in 1st Grade or 1,000 runs in B Grade, reached or coming up. Merged grade names count as one grade and the club\'s own grade names are used. A player who has only ever played one grade is left out, since their career milestone already covers it.',
    'Send me a test email: on Notifications settings, sends you one copy of the notification email straight away with the club\'s recent notifications in it. It only goes to you and does not affect the daily email.',
    'The same section now shows what happened to your last notification email: sent, waiting, or not delivered and why.',
    'With no email provider connected, notification emails now stay waiting instead of being marked as sent when nothing went out.',
    'Fixed: if one kind of notification failed to check, the rest of that club\'s daily check stopped too.',
  ],
}
