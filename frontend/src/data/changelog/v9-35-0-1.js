export default {
  version: 'v9.35.0.1',
  date: '2026-08-20',
  sortKey: '2026-09-03T15:00:00Z',
  title: 'Square connect: what the "Redirect URL" error is, and where to fix it',
  items: [
    'Connecting Square could end on Square\'s own error page, "Application does not have a Redirect URL registered in the Developer Console", after a club had already signed in. That comes from Square and means the BetterCricket application is missing its redirect URL on Square\'s side. The Square page and the setup step now say so, and show the exact URL that has to be registered.',
    'The redirect URL comes from the server now instead of being typed into the page, so the setup instructions are always the address we actually send, and it can be pointed elsewhere if a club runs on another address.',
    'A server set to the wrong Square environment for its credentials is caught before you are sent to Square, with the reason named, rather than becoming the same unexplained error page.',
  ],
}
