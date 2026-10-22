export default {
  version: 'v9.129.1',
  date: '2026-10-23',
  // Above v9.129.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T13:00:00Z',
  title: 'Squads: two of your teams in one grade now keep their own squad',
  items: [
    'When two of your teams play in the same grade, for example the 8th XI and the 10th XI in One Day Grade 6 Black, every game in that grade used to land on one squad and had to be moved by hand each round. Sync now reads your own team\'s name on the fixture ("Applecross 10th XI") and puts the game on the squad with that XI number.',
    'It only steps in when the name states an XI number, the grade\'s usual squad does not carry that number, and exactly one other active squad does. Anything else is left to the grade, as before. A game you picked by hand stays where you put it.',
    'Saving a squad no longer pulls the other team\'s games across, so nothing needs re-linking afterwards. Set the new squad\'s order to its XI number (the 10th XI squad is order 10) and its games follow on the next sync.',
  ],
}
