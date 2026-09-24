export default {
  version: 'v9.90.4',
  date: '2026-09-24',
  sortKey: '2026-09-30T06:00:00Z',
  title: 'Imported matches count as matches everywhere, and a player page loads quickly again',
  items: [
    'StatLab now counts a match from your imported archive as a match played. It used to count only the innings, so a player with a long archive history read far more innings than games once a grade was picked.',
    'A player who batted twice and bowled once in a two-day imported match had that one spell counted twice, and their catches doubled with it. Each part of the scorecard is now added up on its own.',
    'A single player\'s figures no longer roll up every imported season on the platform on the way to the page. That is what made a player page slow to load once a club left junior grades out by default.',
    'The after-the-fact pairing tool no longer pairs an imported match to a synced game that shares no score with it. Those are listed for a person to check instead.',
  ],
}
