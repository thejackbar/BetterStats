export default {
  version: 'v9.77.0',
  date: '2026-09-10',
  // Above v9.76.0's sortKey, or SITE_VERSION never reaches this one. Check
  // origin/main at merge time.
  sortKey: '2026-09-24T06:00:00Z',
  title: 'A club can bring in its whole history in one file',
  items: [
    'Import scorecards from a spreadsheet now takes a whole club history in one file. The one it refused before was 97 seasons and 184,661 rows, a recovered archive going back to the 1920s, and it had to be split into 92 separate uploads, one per season, to load at all.',
    'Raising the file size limit on its own would not have done it. The review screen was sending the entire spreadsheet back to the server every time you matched a player, picked a season or named a grade, which on a 24 MB file is about 145 MB a press. The sheet is read once when you upload it now and kept on the server while you work, so those presses send a few hundred bytes instead.',
    'The review step is quicker for it. The whole archive comes back in about four seconds a press, instead of waiting on the file going up again each time.',
    'An upload is held for an hour while you work through the review. Leave it longer and the screen says so and asks for the file again, rather than importing an empty sheet.',
    'Nothing changes for an ordinary sheet. The same file imports exactly as it did.',
  ],
}
