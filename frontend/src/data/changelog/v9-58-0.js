export default {
  version: 'v9.58.0',
  date: '2026-09-01',
  sortKey: '2026-09-01T18:00:00Z',
  title: 'Segment on whether a club has a primary admin',
  items: [
    'Internal: a new Segments rule, "Club primary admin" — someone is assigned, nobody is assigned, or the club is not on the platform.',
    'Pick "Nobody assigned" to target the clubs a super admin created or synced that no real contact ever took over, or pick the other two to keep them out of a send.',
    'A club that was never onboarded is its own option rather than being counted as having no admin, so excluding the unrun clubs does not also drop every prospect in the directory.',
    'A club admin who was never made the primary still counts as nobody assigned — the question is who owns the club relationship.',
  ],
}
