export default {
  version: 'v9.69.0',
  date: '2026-09-07',
  // The list is ordered by sortKey, and SITE_VERSION is whatever sorts top —
  // so this only has to be greater than the current highest, which is
  // v9-67-4's 2026-09-13T18:00:00Z (several recent entries carry sortKeys
  // ahead of their own dates; that ordering quirk predates this release and is
  // left alone rather than quietly renumbering somebody else's entries).
  sortKey: '2026-09-14T12:00:00Z',
  title: 'Notifications the club sets up itself',
  items: [
    'A new Notifications screen under Account: pick what the club is told about, on email, in the app, or both. Everything the platform can raise is listed there, so nothing is happening that you cannot see and switch off.',
    'Milestones are covered both ways — a player passing 1,000 runs, and a player who is a handful away from their next one. Each is raised once, not every day until somebody notices.',
    'Volunteer and official certifications are watched for expiry: Working With Children checks, RSA, first aid, coaching accreditation. The notice period is yours to set, and anything already lapsed is raised straight away.',
    'Also on the list: a failed data sync, new results landing, gear or a facility due for service, stock running low, and the reports and player requests waiting on somebody.',
    'Everything new goes out as one email rather than one per thing, daily or weekly, whichever the club picks.',
    'Any admin can stop being emailed without changing it for anybody else, and the whole thing can be switched off for the club in one place.',
    'A notification about something only certain people can act on only goes to those people.',
  ],
}
