export default {
  version: 'v9.134.2',
  date: '2026-10-28',
  // Above v9.134.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-11T13:00:00Z',
  title: 'Player Cards: action and hero shots for the cards that matter',
  items: [
    'Changed: cards now use a player\'s photos by what kind of card it is. Common and Rare cards show the profile photo in the circle. Epic cards fill with the hero photo and Legendary cards with the action shot.',
    'Changed: special cards fill with a photo too. A century, fifty, five-for or hat-trick uses the action shot, because it marks a moment in play. A debut, a milestone or an award uses the hero photo.',
    'If a player lacks the shot a card wants, it uses the other one, then the profile photo. A shot pinned on a player\'s profile still wins.',
    'Clubs can choose how far this goes in Settings: special, Epic and Legendary cards (the default), special cards only, or every card that has a big photo, as before.',
  ],
}
