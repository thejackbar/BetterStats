export default {
  version: 'v9.57.1',
  date: '2026-09-01',
  sortKey: '2026-09-01T22:00:00Z',
  title: 'The home page found the milestones it was missing',
  items: [
    'Fixed: MILESTONES IN REACH on a club home page could load for a minute and then say "No upcoming milestones" while Admin → Milestones listed plenty. The panel was not empty — its request was timing out, and the page reported a failure as an empty club.',
    'The home page now works the milestones out the same way the Milestones report and the Records page always have, so the three screens name the same players and the same targets.',
    'That also brings back milestones the home page used to drop: a player closing on their 50th game or 50th catch was left out unless they also had runs or wickets to their name.',
    'A player who has not turned out for three seasons is no longer listed as being two wickets away.',
    'If the milestones genuinely cannot be loaded, the panel now says so instead of showing an empty list.',
    'The panel is labelled BIGGEST FIRST, which is the order it has always used — a 500th run comes before a 50th game two away.',
  ],
}
