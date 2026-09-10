export default {
  version: 'v9.79.0',
  date: '2026-09-10',
  // Above v9.78.0's sortKey, or SITE_VERSION never reaches this one. Check
  // origin/main at merge time.
  sortKey: '2026-09-25T12:00:00Z',
  title: 'A spreadsheet import can correct a wrong Cricket Australia season',
  items: [
    'When Cricket Australia has a match wrong for you, a spreadsheet import can now put it right. Choose "Overwrite existing matches" and a match synced from Cricket Australia is taken over by your file, rather than being skipped. Your version becomes the record for that match.',
    'The whole season the match is in then counts your import instead of Cricket Australia\'s own figures, so a season\'s totals stop reading the wrong numbers. This only happens for the "Overwrite existing matches" choice, and only for the seasons your file actually corrects.',
    'A correction made this way is kept. A later sync from Cricket Australia will not put the old figures back over the matches you took over.',
    'Nothing is deleted. The synced match itself is left in place; your imported copy simply becomes what is shown and counted.',
    'If your file covers only part of a season you have re-sourced, the import tells you how many Cricket Australia matches it did not cover, since those drop out of that season\'s totals. Make sure your file holds every match for the seasons you are correcting.',
    'The result now reports how many matches took over from Cricket Australia and how many seasons were re-sourced, alongside the new and overwritten counts. Undo the whole import from Audit and Undo, and the re-sourced seasons go back to reading Cricket Australia\'s figures.',
  ],
}
