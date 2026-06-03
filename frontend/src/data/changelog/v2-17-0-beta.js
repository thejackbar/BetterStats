export default {
  version: 'v2.17.0 Beta',
  date: '2026-06-03',
  sortKey: '2026-06-04T18:00:00Z',
  title: 'BetterIQ — bug-fix sweep across every screen',
  items: [
    'Season filter redesigned: the cramped dot-timeline that became unselectable past a handful of seasons is now a scrollable, filterable list that scales to 100+ years of history — single season or a compare range.',
    'Team/grade filter no longer shows a duplicate “1st Grade” for every season, and changing the grade now actually filters the dashboards (grades are matched by name across the selected seasons).',
    'Team analysis — Innings phases now read correctly for both batting (how we score) and bowling (what we concede), and no longer contradict themselves; extras are ordered worst-offender-first for coaching; “Quality of our wickets” gains a 10-run histogram of the score we remove batters on; the Batting tab adds five new graphs (total distribution, leading scorers, average by position, dismissal types, score-we-fall-on); captains are ranked by best win record.',
    'Player trends — the search bar gets its own row so it always displays, and the squad filter now visibly lists that squad’s players instead of silently filtering a hidden dropdown.',
    'Match preview — danger players now show their average and dismissal context; “Our edge” lists only current (active) players, not retired names; opponent names and the grade ladder resolve to the real club rather than a shared association label.',
    'Opposition — you can now search by an opposition player’s name (not just their club) and jump straight to their profile; a synced club we share a competition with (e.g. Applecross for High Wycombe) now appears as a scoutable opponent even with no head-to-head history.',
    'Selection — analyse and build a team even when nothing is saved: the page loads a suggested best-available XI from your full eligible squad, lists every squad player’s availability, and lets you add or remove players from the XI right here before sending it back to BetterSelect.',
  ],
}
