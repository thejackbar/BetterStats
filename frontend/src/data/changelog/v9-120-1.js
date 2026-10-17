export default {
  version: 'v9.120.1',
  date: '2026-10-20',
  // Above v9.120.0.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-20T03:00:00Z',
  title: 'Fines is now a dashboard, with picked sides, a maximum and a PDF report',
  items: [
    'The Fines screen is now a small dashboard instead of one long page. Tiles show the pot, what is still to collect, the total fined and the last session. Tabs split it into Overview, Add fines, Tracker, Setup and Report. Overview has a bar for each recent session, how much has been collected, who owes most and who has been fined most.',
    'Add fines now starts with a row for each player picked in the squad\'s side for that week, so you are not hunting for names. Change the date and it loads that week\'s side. If no side was picked it says so, and Whole squad adds everyone.',
    'Fine several players at once: tick them and use Fine ticked, or use Fine all. A player can have more than one line, and each fine can carry a note.',
    'Set a maximum per player per session in Setup. Max all and Max ticked then take each player up to the maximum, counting what they have already been fined that day. Nobody can be taken over it: the screen holds Save back and the server refuses it too.',
    'The new Report tab runs a period (all time, last 30 or 90 days, this year, or your own dates) and downloads it as a PDF: a summary by player, every fine by session with its reason and note, and the payments. Players see a fine\'s note on their own page too.',
  ],
}
