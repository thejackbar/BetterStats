export default {
  version: 'v1.3.0 Beta',
  date: '2026-06-06',
  sortKey: '2026-06-06T12:00:00Z',
  title: 'Import your club’s history — without double-counting',
  items: [
    'New Import tool (Admin → Import Stats): upload your club’s own historical spreadsheet — career totals or season-by-season, in any column layout — and it’s smart-matched and merged with your online data.',
    'No double-counting, ever: where your sheet and the online (Grassroots) data overlap, the online data wins, and only the part it’s missing is added on top. A player who appears in both can’t be inflated.',
    'Upload CSV or Excel. The wizard auto-maps your columns (Games, Runs, HS, Avg, Wickets, Catches…), matches names to your players (fuzzy-matched, you confirm), and matches season labels — including a “Prior Seasons & Adjustments” catch-all.',
    'Summary-only sheets are fine: give us averages and we reconstruct the underlying not-outs/balls (shown with a ±1 note). A live “your sheet + online = final” preview shows the result before you commit.',
    'Fully reversible — every import is listed and can be undone, and it self-corrects automatically as more online data syncs in.',
  ],
}
