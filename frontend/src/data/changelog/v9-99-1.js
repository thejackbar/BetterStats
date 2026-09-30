export default {
  version: 'v9.99.1',
  date: '2026-09-30',
  // Above v9.99.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-06T12:00:00Z',
  title: 'New players are matched to their PlayCricket profile',
  items: [
    'Adding a player now asks you to find them on PlayCricket and confirm they are joining your club, or to say they are not on PlayCricket yet. Picking the person stores their PlayCricket id on the record, so their first synced game lands on the player you created instead of creating a second copy.',
    'Fantasy has the same step on its new-player form. It also reads the person’s recent record at their previous club and suggests a role and starting price, using the same pricing as the rest of the pool. You can still type your own price, and a price you have typed is never overwritten.',
    'Players you have already created can be matched from their profile, under PlayCricket profile. Nothing is saved until you press Link.',
    'For players created any other way (nets registrations, imports), the sync now ties a newly seen PlayCricket player to a hand-made player of the same name, but only when exactly one fits, the feed does not name two people alike, and the hand-made player has no games or stats yet. Anything less certain is left alone and still shows up in Merge Duplicates.',
    'The old Player ID box on the Add player form is a reference field only. It never matched anyone to PlayCricket, and is now labelled that way.',
  ],
}
