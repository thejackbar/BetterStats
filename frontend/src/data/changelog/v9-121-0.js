export default {
  version: 'v9.121.0',
  date: '2026-10-24',
  // Above v9.120.6's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-24T18:00:00Z',
  title: 'The Primary Admin can limit a colleague to one module',
  items: [
    'On Club Users, the Primary Admin can now choose what each person can open. Pick Add user, or open someone already there, and choose One module only. Then pick BetterStats, BetterSelect, BetterSocials, BetterIQ, BetterFantasyCricket or BetterAdmin.',
    'A person limited to a module sees every screen in it and nothing else: no Settings, no Users, no Plan & Billing and no other module. Their dashboard shows only their module and the quick links they are allowed to use.',
    'Everyone still starts with access to everything, and nobody changes until the Primary Admin limits them. Only the Primary Admin, or BetterCricket support, can change what someone can open. The person who signed a club up is its Primary Admin.',
    'A limited person stays in their own club. They do not get the club switcher, even when the club is linked to others.',
    'The Primary Admin is now protected. Another admin can no longer remove them, edit their account or send them a password reset.',
    'An admin who has switched into a linked club can no longer invite, edit or remove that club\'s users. Do that from your own club.',
    'About 80 screens that used to let any signed-in person through now check permission. They include Manual Entries, Players, Partnership Records, Data Sync, and BetterSelect availability, selection, squads and nets. Admins with full access see no difference.',
    'A saved StatLab report can now be deleted only by whoever saved it or by someone who manages reports.',
  ],
}
