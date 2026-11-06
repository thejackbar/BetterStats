export default {
  version: 'v9.129.31',
  date: '2026-10-26',
  // Above v9.129.30.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T20:00:00Z',
  title: 'One voting link that takes players to their next game',
  items: [
    'The voting link now works as one portal. A player opens it, finds their name, enters their PIN and lands on the next game they played that is open for voting and that they have not voted on. After each ballot it offers the next one, until there is nothing left. Anyone already signed in on that phone goes straight to their next game.',
    'The games list is still there under "See all my games", for changing a ballot already cast. A link to one game still opens that game.',
    'On a team set to captain only, or to chosen people, the rest of the side is no longer offered its games, since there is nothing for them to vote on.',
    'In Votes, the voting link now sits at the top of every tab, shown like the availability link: the link and a Copy link button. The WhatsApp, SMS, message preview, QR and per-team and per-game links are gone, because one link does the job. If the link is off, the same spot says so and has a button to turn it on.',
  ],
}
