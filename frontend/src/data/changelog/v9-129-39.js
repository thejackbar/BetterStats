export default {
  version: 'v9.129.39',
  date: '2026-10-26',
  // Above v9.129.38.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-09T03:00:00Z',
  title: 'Sell several players at once on Transfers',
  items: [
    'New: on Transfers you can tick more than one player to sell. Bank moves as soon as you pick someone to sell and shows what it will be once your picks are in, so you can see what you can afford before you choose a replacement.',
    'New: the swaps go through together and the budget is checked over the whole set, so selling two players to pay for one dearer pick works. On a phone, pick who is leaving, tap Next, then choose the replacements.',
    'New: the player pool on Transfers sorts by Player, Price, Sel and Total. Tap a heading again to flip the order.',
    'Fixed: transfers queued behind a locked round are now carried out together when the round is scored. A swap that only the other sale could pay for used to be cancelled.',
  ],
}
