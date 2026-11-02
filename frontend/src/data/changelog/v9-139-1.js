export default {
  version: 'v9.139.1',
  date: '2026-11-02',
  // Above v9.139.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T11:00:00Z',
  title: 'Milestones can be filtered by age group and by when a player last played, and grades a player has left stop showing',
  items: [
    'New: Milestones has an age group filter (Seniors and Juniors, plus Women\'s or Masters where your club has them). A player who turned out in both kinds of grade in their newest season shows under both. It only appears when your club has more than one group.',
    'New: Milestones has a Last played filter. Pick This season, or the last 2, 3, 5 or 10 seasons, counted back from your current one, and anyone who has not played since drops off the list. A player we cannot place keeps their rows rather than being hidden on a guess.',
    'Fixed: a player could show as one game short of a milestone in a grade he last played years ago (one game from 50 in 1st Grade, last played there over twenty years ago). A grade milestone now only shows while the player has played that grade in the last three years.',
    'Fixed: a grade your club has no side in this season no longer shows upcoming milestones, on the Milestones page, the Records grade view, the player profile and the milestone notices. Milestones already reached stay on the list.',
  ],
}
