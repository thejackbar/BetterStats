export default {
  version: 'v8.50.2.1',
  date: '2026-07-02',
  sortKey: '2026-07-02T09:00:00Z',
  title: 'Full Rebuild reliability',
  items: [
    'Fixed Full Rebuild aborting with "All connection attempts failed" when the Cricket Australia stats API dropped a single connection mid-sync. It now retries a dropped connection a few times before giving up on that page of data, instead of failing the whole rebuild.',
    'Super Admins can now run Full Rebuild as many times as needed, without the once-per-hour limit that applies to club admins.',
  ],
}
