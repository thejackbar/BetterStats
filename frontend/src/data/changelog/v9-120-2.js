export default {
  version: 'v9.120.2',
  date: '2026-10-21',
  // Above v9.120.1.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-21T03:00:00Z',
  title: 'Vote reminders on the player\'s own page',
  items: [
    'If you played in a game that is still open for voting and have not voted yet, your My page now says so. A banner at the top shows how many votes you have to cast, a Votes due tile counts them, and a Votes to cast list shows each game with the medal, the round and when voting closes. Each has a Vote button.',
    'The button opens that game\'s ballot with your name already picked, so you only type your PIN. Once you have voted, the reminder goes away. It never shows for a game you did not play, one the club has locked or one past its closing date, and in a captain-only count only the captain is reminded.',
    'Votes is part of the default page, and shows nothing when nothing is due. Clubs that picked their own modules can tick Votes in Availability under Self-service link, Player page.',
  ],
}
