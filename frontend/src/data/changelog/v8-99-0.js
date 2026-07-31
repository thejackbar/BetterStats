export default {
  version: 'v8.99.0',
  date: '2026-07-31',
  sortKey: '2026-07-31T15:00:00Z',
  title: 'Build BetterComms lists straight from the CRM pipeline',
  items: [
    'CRM Sales Pipeline: a new set of stage filter buttons below the module chips (on both Board and List views), one per pipeline stage. Each cycles off → exclude (red) → include (green), the same way the Club Directory category filters work. Your selection is saved to your account and restored next time you open the page.',
    'CRM Sales Pipeline: a new "Create List" button (between Dashboard and Recalculate) turns the deals currently shown into a BetterComms list, one contact per deal. It finds each deal\'s contact (the deal\'s point of contact, or the club\'s President, then Secretary, Treasurer, or default email), matches it to your existing BetterComms contacts, and asks you to resolve any that don\'t match by picking one of the club\'s contacts or typing a name and email. Anyone left without a valid email is flagged before the list is created.',
    'BetterComms → Lists now groups lists into "Your lists" (created by hand) and "Auto-generated lists" (built by tools like the CRM Sales Pipeline).',
  ],
}
