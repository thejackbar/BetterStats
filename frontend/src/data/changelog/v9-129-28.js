export default {
  version: 'v9.129.28',
  date: '2026-10-25',
  // Above v9.129.27.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T16:00:00Z',
  title: 'Choose the people who vote for a team',
  items: [
    'In Votes, Settings, under "Who votes, by team", a team can now be set to Chosen people. Pick the people who decide that team\'s votes: the captain and a couple of selectors, say, or anyone else in the club. Up to 12 people, and they do not have to be in the side.',
    'Each chosen person signs in on the voting link like any player, sees only that team\'s games and submits their own ballot. Their ballots add up and are turned into the game\'s 3-2-1 the same way as when every player votes. Everyone else on the team, the captain included unless they are chosen, is told the votes come from the chosen people.',
    'The Games list and each game now expect a ballot from the chosen people, not the whole side, and the reminder to those who have not voted goes only to them. Their own page lists the game as a vote due. If a team is on Chosen people with nobody picked, nobody can vote for it, and Settings says so.',
    'This replaces the single "Votes counted by" person from the last release. A team that had one nominated person is moved across to Chosen people with that person on the list, so nothing changes for it.',
  ],
}
