export default {
  version: 'v9.106.22',
  date: '2026-10-05',
  sortKey: '2026-10-05T11:00:00Z',
  title: 'Closed two holes in the player routes: anyone could rename a player, and any club could read another club\'s players',
  items: [
    'Anyone, with no login, could change any player\'s name at any club through a route the site itself never used. That route is gone. Renaming a player still works from the club admin screens.',
    'A club admin could read and edit another club\'s player profile (email, phone, date of birth, selection details) if they had the player\'s id. A club admin now only reaches their own club\'s players.',
    'A player who has asked to be removed can no longer have their profile claimed by someone else.',
  ],
}
