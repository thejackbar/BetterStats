export default {
  version: 'v9.129.22',
  date: '2026-10-25',
  // Above v9.129.21's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T09:00:00Z',
  title: 'Fantasy: running points now count for teams that joined late',
  items: [
    'Fixed: after the round dates were fixed, every team still showed 0 points and the ladder was all zeros. Teams that joined while round 4 was the open round were set to score from round 4, so round 3, which is the live round again, was skipped for all of them. Pressing Sync scores now moves those teams back onto round 3 and gives them their running points straight away.',
    'My Team now shows the round being played: the GW tile reads "GW3 live" with the team\'s running points, and each player shows his points so far, refreshing every minute. Before, it only showed the last round that had been confirmed, so a team with none showed dashes while the round was live.',
  ],
}
