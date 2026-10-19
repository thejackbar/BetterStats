export default {
  version: 'v9.120.6',
  date: '2026-10-24',
  // Above v9.120.5's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-24T12:00:00Z',
  title: 'Emails to a big list no longer take days, and subscribing lifts your sending limit',
  items: [
    'A club that subscribes to BetterAdmin now moves to the Production sending limit on its own, instead of staying on the 50-a-day trial limit until someone asked for it. If a club cancels or pauses, it goes back to the trial limit. A failed payment on its own changes nothing.',
    'Emails held back by a daily limit now go out every morning. Before, a club on the 50-a-day limit only got a batch every second day, so a 669-person email took more than a week to reach everyone. The day now starts at midnight UTC (8am in Perth) and the next batch runs at 8:15am Perth time.',
    'Before you press Send, the email screen tells you if your sending limit means only some people get it today, how many are held back and when the next batch goes. The same note shows on a sent email while people are still waiting.',
    'Clubs that already subscribe to BetterAdmin and were still on the 50-a-day limit are lifted to Production in one pass by support.',
  ],
}
