export default {
  version: 'v9.32.0',
  date: '2026-08-19',
  sortKey: '2026-08-30T09:00:00Z',
  title: 'Hiding a player, two new selection filters, and grade filters in BetterIQ',
  items: [
    'A player can be kept off the public website. Their profile page stops resolving and they drop off the squad list, the search box, the leaderboards, the records and the milestone shelves. Their runs and wickets still count towards the club\'s own totals, and every admin screen still shows them, so selection, fees and reports are unaffected. Set it on the player\'s profile; the Players screen has a Hidden filter listing everyone who is opted out. Asked for by junior players who would rather not be findable.',
    'Upload Scorecard can add what the card names. A name nobody on the roster answers to offers itself for adding right where the search comes up empty, and seasons and grades can be created without leaving the review. An old card that names a season we never synced, a grade that has since folded, or a player who has just joined is no longer a dead end.',
    'BetterSelect can filter the pool by fees owing and by training attendance. Fees reads the balance BetterFees already works out; training reads who has been at nets in the last three weeks. A club running neither can set both by hand on a player\'s profile instead. Anyone the club has no answer for shows under "Not known", which is the list still to be chased.',
    'Match posts use each club\'s own colours and crest. Both sides used to get the same blue and red whoever was playing, so a club posting about its own game came out in someone else\'s colours.',
    'Long club names no longer run into the crests on a lineup post, or push the score off a scorecard post. A crest that fails to load falls back to the club\'s initials rather than a broken image.',
    'BetterIQ has the Grade Type and Match Type filters the rest of BetterStats already carries. Tick any combination, such as One Day and T20 together. Grade type left blank uses the club\'s own default; match type left blank applies no filter at all, since plenty of older games have no format recorded. A few boards read from season totals and genuinely cannot answer either filter, and they now say so rather than showing unfiltered figures.',
  ],
}
