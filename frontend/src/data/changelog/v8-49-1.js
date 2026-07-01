export default {
  version: 'v8.49.1',
  date: '2026-07-01',
  sortKey: '2026-07-01T13:00:00Z',
  title: 'Login attempt log',
  items: [
    'Every sign-in attempt is now recorded, so we can see which username or email someone tried, whether it worked, and roughly where it came from. Before this the app only kept a failure counter on each account and never stored what was actually typed.',
    'There is a new Login Attempts page under the super-admin menu. Filter to failures only or search by username, and each row shows the outcome, the account and club if the name matched a real login, the country and device, and a one-way hash of the IP.',
    'The password is never stored, and the IP is kept as a hash rather than the raw address. Repeated failures from one IP hash against different usernames is the pattern worth watching for.',
  ],
}
