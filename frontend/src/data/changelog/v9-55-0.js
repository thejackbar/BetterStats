export default {
  version: 'v9.55.0',
  date: '2026-08-31',
  sortKey: '2026-08-31T09:00:00Z',
  title: 'Segment a club by where its trial stands, and write the days into the email',
  items: [
    'BetterComms → Segments can now pick contacts by the state of their club’s trial: running now, expired, or no trial on record.',
    'Two number rules go with it — "Days left in trial" (at most 7, for a club about to run out) and "Days since trial expired" (at most 30, to reach a club while it is still worth reaching).',
    'Three merge variables to splice into a template: {{trial_days_left}}, {{trial_days_since_expiry}} and {{trial_end_date}}.',
    'The figure the email prints is the figure the audience was picked on — both come from one definition, so a segment built as "at most 7 days" cannot send an email that says 9.',
    'A club that is not on a trial renders the figures blank, never as 0.',
    'A trial with no end date reads as running and never as expired, so a club still using the product is never told its trial has finished.',
    'Internal only: these rules are BetterCricket super-admin, on the Clubs Directory audience. The server now refuses them outright for a club rather than relying on the query returning nothing.',
  ],
}
