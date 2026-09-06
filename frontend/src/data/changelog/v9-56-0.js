export default {
  version: 'v9.56.0',
  date: '2026-09-01',
  sortKey: '2026-09-01T09:00:00Z',
  title: 'Club admins keep an internal contact list up to date on their own',
  items: [
    'Internal: a club admin now lands on BetterCricket’s "Super Admin User Contact List" the moment they become one — a self-serve registration, a super admin creating a club, a primary admin being reassigned, an admin added to an existing club, or a club member promoted to admin.',
    'Every club admin counts, not only the primary one, so the list keeps matching the roster as clubs add people.',
    'Each contact is linked to the club’s Clubs Directory row, so {{club}} and the trial countdown resolve when you email them.',
    'Somebody who has unsubscribed or bounced keeps their contact details current but is never put back on the list.',
    'The list is never rebuilt from scratch: an existing list of that name is adopted, and re-running adds nobody twice.',
    'A one-off backfill script puts everyone who is already a club admin on the list, dry-run by default.',
  ],
}
