export default {
  version: 'v9.48.1.1',
  date: '2026-08-22',
  sortKey: '2026-08-22T19:00:00Z',
  title: 'The trial-offer voicemail email is findable in Comms - Templates',
  items: [
    "\"Email following voicemail - trial offer\" (Send an Email's Template list) seeded its Comms -> Templates record under a shortened name, \"Email following VM. Trial offer\", so searching Comms -> Templates for what the dropdown actually says found nothing. It's renamed to match exactly, and self-heals on the next Send an Email load.",
    'Hardened the same seeding step against a second, related gap: a built-in sales template whose Comms Template row already existed under the right name but with no machine-readable key attached could make the whole Template list fail to load. That key is now backfilled first, so it can no longer happen.',
  ],
}
