export default {
  version: 'v9.129.3',
  date: '2026-10-22',
  // Above v9.129.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T16:00:00Z',
  title: 'Squads: a team sharing a grade is found by its squad\'s name',
  items: [
    'Two squads for teams in the same grade (the 8th XI and a squad called OD6 Black 2, both in One Day Grade 6 Black) still did not split if Cricket Australia\'s name for your team has no XI number in it. Sync now also reads the squad\'s own name or short name: "Applecross OD6 Black 2" goes to the squad called "OD6 Black 2". The club name at the front is ignored.',
    'It only steps in when exactly one active squad has that name and the grade\'s usual squad does not. Two squads with the same name, or a different team that only ends the same way ("Applecross Women OD6 Black 2"), are left to the grade.',
    'Creating or renaming a squad now picks up its games that are already synced, so you do not have to wait for the next fixtures sync. A game you picked by hand stays where you put it.',
  ],
}
