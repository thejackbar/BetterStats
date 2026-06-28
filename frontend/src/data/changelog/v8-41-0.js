export default {
  version: 'v8.41.0',
  date: '2026-06-28',
  sortKey: '2026-06-28T01:00:00Z',
  title: 'BetterComms: contact filters, suppressed view and email consistency checks',
  items: [
    'The Contacts page now has the same Clubs Directory filters as Lists, so you can narrow by club, association, UTM code or state and search across all of them.',
    'New Active / Suppressed toggle on Contacts and Lists. Suppressed covers anyone who has bounced, complained, unsubscribed or been excluded, and suppressed contacts are marked in the list.',
    'Compose now remembers which template an email was started from. The template stays selected when you reopen the email, and it only asks before replacing your message when you switch to a different template.',
    'Compose checks your email as you type and flags inconsistencies: a {{variable}} that is not a real merge field, or a UTM variable used in the body with no matching value set in UTM link tracking. The Emails list shows a warning count for each email.',
  ],
}
