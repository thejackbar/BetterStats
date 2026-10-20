export default {
  version: 'v9.106.30',
  date: '2026-10-06',
  sortKey: '2026-10-06T12:00:00Z',
  title: 'Clubs can choose how often run and wicket milestones are marked',
  items: [
    'The Milestones screen in BetterStats has a new "Milestones tracked" panel. Pick runs every 250, 500 or 1,000 and wickets every 25, 50 or 100. Clubs that change nothing keep the current list: 500 then every 1,000 runs, and 50 then every 100 wickets.',
    'The choice applies everywhere milestones show: the admin report, the public Records page, the dashboard, player profiles, BetterIQ and the milestone emails. A player 10 runs short of 750 now appears as in reach when the club tracks every 250.',
    'When a club picks a smaller step, the rungs it adds are filled in for existing players as history. A veteran past 1,000 runs gets 250 and 750 added with no date, so nobody is emailed that they just reached a milestone from years ago. Their existing dates are kept.',
    'Going back to a larger step hides the extra rungs and keeps them stored, so they return if the club picks the smaller step again. Matches and catches stay at every 50. You need the Milestones permission to change the steps.',
  ],
}
