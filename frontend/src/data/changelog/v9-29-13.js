export default {
  version: 'v9.29.13',
  date: '2026-08-18',
  sortKey: '2026-08-26T09:00:00Z',
  title: 'Trial nudge emails are editable templates, not code',
  items: [
    'The six automated trial emails BetterCricket sends a club admin — trial started, ending soon, ended, converted, "got older stats?" and "haven\'t opened this module yet" — now read their wording from real templates in Comms → Templates on the BetterCricket outreach org, so they can be reworded without a deploy.',
    'Each one is seeded once with its current wording and never overwritten after that, so an edited template stays edited.',
    'Templates use the same {{first_name}} / {{club}} / {{module}} merge tokens as the rest of BetterComms, plus {{trial_end_date}} and the CTA links.',
    'Nothing about who gets these emails or when changed. They are still transactional sends straight to the club admin, not campaigns, so they carry no unsubscribe link and count against no send allowance.',
  ],
}
