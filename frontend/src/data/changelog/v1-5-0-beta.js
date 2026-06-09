export default {
  version: 'v1.5.0 Beta',
  date: '2026-06-08',
  sortKey: '2026-06-08T12:00:00Z',
  title: 'Unified data pipeline + smarter Fall-of-Wicket analysis',
  items: [
    'Match data now comes through a single unified pipeline — a legacy connection has been retired. Upcoming fixtures, recent results, club win/loss and the full scorecards all run off the same data pipeline.',
    'Scorecards are DB-first: a game we’ve already synced renders instantly from our database; a live or not-yet-synced match falls back to fetching the scorecard live — so you can open a card while a game is still in progress.',
    'Fall of Wickets now names the dismissed batter on both teams’ innings (previously the opposition’s wickets were anonymous), so collapses read clearly on every scorecard.',
    'BetterIQ opposition scouting is now DB-first too: when the team you’re scouting is itself a BetterStats club, the dossier is built from data we already hold instead of re-fetching it live — faster, and it tells you so.',
    'New “Collapse-causers” insight on the Team page (Bowling tab): which of your bowlers take wickets in bursts (3+ in an innings — the spells that trigger a collapse) and at what economy. The same measure is available for synced opponents.',
    'Two legacy match pages were removed — all match links now go to the single, faster database-backed scorecard.',
  ],
}
