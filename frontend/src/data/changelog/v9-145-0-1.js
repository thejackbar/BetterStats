export default {
  version: 'v9.145.0.1',
  date: '2026-11-17',
  // Above v9.145.0's sortKey (2026-11-21T07:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-21T08:00:00Z',
  title: 'Redraw every season picture after a wording change',
  items: [
    'Super Admin (server): render_club_teasers has a new --before option. It redraws every club whose season picture was drawn before a given time, a batch at a time, and each run carries on from where the last one stopped. Use it after changing what the pictures say.',
  ],
}
