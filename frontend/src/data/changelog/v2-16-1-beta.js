export default {
  version: 'v2.16.1 Beta',
  date: '2026-06-04',
  sortKey: '2026-06-04T12:00:00Z',
  title: 'Clubs that share grades now pick up all of them',
  items: [
    "Fixed: a club only saw the grades unique to it, in the Grade filter, and when auto-seeding squads in BetterSelect, if it shared competition grades (like 1st Grade or One Day Grade 2) with another club already on BetterStats. A grade is a competition-wide thing shared by every club in it, so it's now scoped per club. After a re-sync, every grade your teams actually play in shows up, and their game-level scorecards sync too.",
  ],
}
