export default {
  version: 'v9.137.2.4',
  date: '2026-11-01',
  // Above v9.137.2.3's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-14T23:30:00Z',
  title: 'Fantasy transfers: captains can be sold',
  items: [
    'Fixed: Confirm transfer did nothing when the player going out was your captain or vice-captain. The server refused it and the reason showed in a banner at the top of the page for a few seconds, so on a phone it looked like the button was dead. The player coming in now takes the armband, the same as a transfer queued behind a locked round already did.',
    'You can now pick replacements who cost more than your bank while you work out a set of transfers. The bank turns red, the screen says how far over you are, and only Confirm is held back until the set fits.',
    'When the swap row shows a captain or vice going out, it is tagged so you can see who is taking over.',
    'A transfer that is refused now says why on the Transfers screen, next to the button, and stays there until you change the set. The wording names the players and the figures, for example how much you are over budget, what the sale returns and what the replacements cost.',
  ],
}
