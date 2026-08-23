export default {
  version: 'v9.9.0',
  date: '2026-08-05',
  sortKey: '2026-08-08T09:00:00Z',
  title: 'Import Awards — bring your whole honour board in from a spreadsheet (BetterFootball)',
  items: [
    "A new Import Awards tool takes a club's honour board from a spreadsheet: upload it, check the columns, match the names, and see exactly what will be recorded before anything is saved. Built the same way as Import Stats and Import Results, and undoable in one click.",
    "An award your club doesn't have an award type for yet is added to your catalogue as part of the import, so the honour board and the Awards dropdown agree afterwards. A trophy you already have is matched and keeps the category you filed it under.",
    'Names are matched to your players the same way Import Stats does it: exact matches confirmed in one pass, close ones offered for you to check, and anything with no match becomes a new player rather than being dropped.',
    "If your sheet carries its own player ID, map it. Two spellings of one name are then treated as one person, and two different people who share a name are kept apart and put in front of you to split rather than having one person's honours land on the other's profile.",
    'A row that names no award is skipped and counted, so a sheet that also records who turned out each year can be uploaded exactly as it is.',
    'Re-uploading a corrected sheet adds what is new and leaves what is already recorded alone, so nothing doubles up.',
    "Categories are worked out from the award's own name. Life Membership, Hall of Fame, premierships and games and goals milestones each land in the right place, and every one of them can be changed before you import.",
  ],
}
