export default {
  version: 'v9.106.9',
  date: '2026-10-05',
  sortKey: '2026-10-05T12:00:00Z',
  title: 'Fantasy: merge a hand-added player into their real profile from the Fantasy page',
  items: [
    'A player added to Fantasy by hand has no games of their own. When their real games sync they land on a separate profile with the same name, so the hand-added player scores nothing while the points sit on the other profile.',
    'Fantasy > Registered players now has a card that lists each of these pairs, with how many games the real profile has and how many teams picked the hand-added player. Press Merge, confirm, and the two are merged. The teams that picked them keep the player under the real profile, the pool entry moves across, and the scored rounds are scored again so the points show straight away. It can be undone from the merge log like any other merge.',
    'Only a pair the card shows can be merged from there, and it needs the Merge data permission as well as the Fantasy one. Players added by hand who have not played yet are listed underneath, with nothing to do until a profile with the same name has a game.',
    'Merging a player never loses them from a team. Every Fantasy record that points at a player (team picks, the pool, round points, captain and vice-captain marks, the transfer history, draft picks and waiver claims) is moved to the kept profile, and a check now fails if a Fantasy table is ever added without being moved too.',
  ],
}
