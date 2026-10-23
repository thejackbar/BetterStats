export default {
  version: 'v9.129.10',
  date: '2026-10-23',
  // Above v9.129.9's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T23:45:00Z',
  title: 'Ask BetterIQ no longer says "System refreshing" on a long question',
  items: [
    'A longer question to Ask BetterIQ, such as one comparing two clubs, could take more than a minute to work out. The server in front gave up at 60 seconds and the page showed "System refreshing. Please wait a moment…", as if the site were down. Ask BetterIQ now gets five minutes to answer.',
    'If a question still runs too long, you now get a plain message saying so and suggesting a narrower question, instead of the refreshing notice.',
  ],
}
