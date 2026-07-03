export default {
  version: 'v8.55.0',
  date: '2026-07-04',
  sortKey: '2026-07-04T06:00:00Z',
  title: 'BetterComms sending limits',
  items: [
    'Every club now starts on the sandbox sending tier and earns production by asking. A bug was flipping all clubs to production on every restart, which is now fixed.',
    'The "Sent today" figure now counts your real sends over the last 24 hours and shows how many you have left today.',
    'Added a monthly sending limit on top of the daily one, with a per-club figure a super admin can set.',
    'Bounce and spam rates now show the real number instead of a dash, plus a delivered count.',
    'A super admin can set the default daily and monthly limits for all clubs from the sending limits page.',
    'The club logo now shows in emails you write from scratch, and a sent email\'s status updates on its own without a refresh.',
  ],
}
