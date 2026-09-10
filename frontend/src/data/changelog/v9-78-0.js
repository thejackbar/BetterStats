export default {
  version: 'v9.78.0',
  date: '2026-09-10',
  // Above v9.77.0's sortKey, or SITE_VERSION never reaches this one. Check
  // origin/main at merge time.
  sortKey: '2026-09-25T06:00:00Z',
  title: 'Choose what happens to a match a spreadsheet already has',
  items: [
    'Importing scorecards from a spreadsheet now asks what to do with a match you already have in BetterCricket, before it writes anything. Pick "Only import new matches" and any match already there is left alone and the duplicate in the sheet is discarded. Pick "Overwrite existing matches" and the sheet\'s version replaces the one you have.',
    'A match counts as one you already have when it shares a date and opponent with an existing record. A match with no date or opponent in the sheet is always brought in as new.',
    '"Only import new matches" is the default, so a re-upload never quietly doubles up a match or writes over what you entered by hand.',
    'A match already synced from Cricket Australia is never overwritten by a spreadsheet. When it lines up with one, the sheet\'s copy is skipped so the game is not counted twice.',
    'After the import you get the count of new matches, matches overwritten, and matches ignored because they were already there. The whole import, overwrites included, still comes back in one go from Audit and Undo.',
  ],
}
