export default {
  version: 'v8.99.2',
  date: '2026-07-31',
  sortKey: '2026-07-31T20:00:00Z',
  title: 'Self-serve trial deals now keep the registering admin as their contact',
  items: [
    'Fixed a bug where a club that registered through the self-serve trial flow got a Sales Pipeline deal with an empty Contact Name, Email and Mobile, even though the sign-up captured all three. New self-serve deals now link the registering admin as the point of contact.',
    'Every other automatic way a deal reaches the pipeline (a trial started or requested, a bulk push from the Club Directory, an engagement auto-add, an enquiry or a stalled wizard lead) now seeds the deal\'s contact from the club\'s best-known details too.',
    'Existing deals that were created before the fix can be repaired with the new backfill script, which links each contactless deal to its club\'s best-known contact.',
  ],
}
