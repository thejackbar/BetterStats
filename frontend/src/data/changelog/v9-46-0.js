export default {
  version: 'v9.46.0',
  date: '2026-08-21',
  sortKey: '2026-08-22T09:00:00Z',
  title: 'Squads: the unassigned list is the players you are actually picking from',
  items: [
    'The unassigned side of the Squads board is three groups instead of one. Unassigned is now just active players who are still around and have no squad, so the list a selector reads is the list they can pick from.',
    'Potential fill-ins holds anyone who has dropped off, with a control for how far back to dig. Not yet played holds a new signing who has no game against their name yet. Nobody is dropped, and a card in any group still drags straight into a squad.',
    'Players marked inactive are off the board. The board says how many it is holding back, and there is a Show inactive players filter when you need one of them.',
    'Marking someone inactive now takes them out of their squad, from the player profile, the bulk action on Players, the Directory and a profile import alike. Auto-assign stopped suggesting squads for them too.',
    'The split uses the club\'s own dormancy setting, the same one Availability and Selection already work from, rather than a separate number on this screen.',
    'A card shows the year a dormant player last turned out, which is the thing you weigh when you are looking for a fill-in.',
    'Fixed while here: assigning a squad from the Clubhouse Directory did not update the squad list the Availability and Selection screens read, so the two could disagree about who was in a squad.',
  ],
}
