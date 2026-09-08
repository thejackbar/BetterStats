export default {
  version: 'v9.70.0',
  date: '2026-09-15',
  // Above v9.69.8, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-15T09:00:00Z',
  title: 'Club Directory reads the committee PlayHQ publishes today',
  items: [
    'New Rediscover button on the Club Directory: re-reads every club\'s committee from PlayHQ and brings the directory into line with it. There is a per-club version on each club card too, which answers in a second or two.',
    'Officers PlayHQ still lists get their current role, and are ticked for outreach if they have an email address.',
    'Officers PlayHQ has dropped are removed. One who unsubscribed, bounced, was marked do-not-contact, carries a note or is linked to the CRM is kept and badged "not on PlayHQ" instead — removing them would let the next crawl add them back as a fresh, ticked contact.',
    'Contacts you added by hand are never touched, and nobody is ever removed from BetterComms.',
    'Exporting to BetterComms now updates a contact who is already there rather than skipping them, so a change of role reaches your audience. Somebody who has since left the committee keeps the last role we knew them by.',
    'Role is a new filter on Lists and Segments, so "email every Secretary" is an audience you can build.',
    'A "Tick officers with an email" button applies the same ticking rule to the clubs you have filtered, with no PlayHQ traffic, when you do not want to wait for a full re-read.',
  ],
}
