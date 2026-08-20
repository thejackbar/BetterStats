export default {
  version: 'v9.35.0',
  date: '2026-08-20',
  sortKey: '2026-09-04T09:00:00Z',
  title: 'Picking a club in the registration wizard now counts towards its engagement score',
  items: [
    'A club someone picked by name in the registration wizard earns 15 points on its engagement score, once for each person who picked it. A club two or three different people went looking for now reads warmer than one nobody has, which is what you would expect and what the score used to miss entirely.',
    'These selections never scored before. The wizard sits on the /trial page, which belongs to no club, so the score had no way to tell whose selection it was. It now matches on the club the visitor actually picked.',
    'One person clicking the same club several times counts once. The score follows the number of people, not the number of clicks.',
    'A selection you have flagged as test noise on the Meta Ads page does not score, so your own test runs cannot push a real club up the board.',
    'Past selections count too. Run app.scripts.backfill_wizard_selection_points to bring the existing clubs up to date; it shows what would change before you commit to anything.',
  ],
}
