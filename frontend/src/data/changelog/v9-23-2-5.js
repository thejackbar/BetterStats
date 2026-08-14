export default {
  version: 'v9.23.2.5',
  date: '2026-08-14',
  sortKey: '2026-08-14T17:00:00Z',
  title: 'Merging a player created by a historical stats import could wipe out their imported career',
  items: [
    'A player minted by BetterImport (Import Stats) because their name didn\'t match anyone already on the roster carries their uploaded totals as their own imported_stats rows. Merging that player into an existing one deleted the player record without ever moving those rows across — so the entire imported career (every season the club\'s spreadsheet gave them) vanished the instant the merge completed, leaving only whatever the surviving player already had.',
    'It was also unrecoverable from Merge Players → History — Undo only restores what the merge log recorded moving, and the imported rows were never recorded at all; they were simply gone.',
    'Fixed: a merge now carries the removed player\'s imported_stats rows across to the kept player (recorded for Undo, same as every other table this applies to) and rebuilds their reconciled totals immediately, so the merged player shows the correct combined career straight away.',
  ],
}
