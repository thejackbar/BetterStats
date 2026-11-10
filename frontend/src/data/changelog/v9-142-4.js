export default {
  version: 'v9.142.4',
  date: '2026-11-10',
  // Above v9.142.3.1's sortKey (2026-11-19T08:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T09:00:00Z',
  title: 'Staff can now block a club from registering or signing in',
  items: [
    "There is now a block list. A club, a club name, a Cricket Australia id, an email address or an email domain can be put on it, and the sign-up form refuses them at the first step.",
    "A club that is already registered can be blocked too. Its members cannot sign in, and a session that is already open stops on its next request. Nothing in the club is deleted.",
    "A blocked club cannot register again under a different spelling of its name.",
  ],
}
