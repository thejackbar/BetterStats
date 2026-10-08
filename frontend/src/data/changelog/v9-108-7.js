export default {
  version: 'v9.108.7',
  date: '2026-10-08',
  sortKey: '2026-10-08T15:00:00Z',
  title: 'A hand-typed player with the same name as a removed person is held until you check',
  items: [
    'A player a club typed in by hand, or imported without a Cricket Australia id, used to slip past a removal because there was no id to match. The record of a removed person now keeps their name, and a new player with the same first and last name is held hidden straight away.',
    'Only a full first and last name counts, in any order or case. A different first name, a lone surname, an initial and surname, or the same name with a different Cricket Australia id are not held.',
    'On a held player\'s profile, BetterAdmin shows "Held: same name as a person who asked to be removed". If they are someone else, "This is a different person" (with a confirm step) puts them back on the public site, and the club\'s choice is kept so they are not held again.',
    'A person\'s own request cannot be released from the club\'s screen. Putting that person back is still done by BetterSports, and it lets their name matches go too.',
  ],
}
