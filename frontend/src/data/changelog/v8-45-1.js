export default {
  version: 'v8.45.1',
  date: '2026-06-30',
  sortKey: '2026-06-30T11:00:00Z',
  title: 'Honour board photo reader and full player search when linking awards',
  items: [
    'The honour board reader on the Awards page now handles photos and scanned boards. It used to come up empty on anything that was not a PDF with selectable text. It now reads the columns from a photo or screenshot, keeps full names in one piece, and ignores the ruled lines of a bordered table. A PDF exported from Word, Excel or Google Sheets still reads the most accurately, and the CSV template is there too.',
    'After a bulk award import, the step that links names to players now searches your whole player list, not only the close matches it found. Linking is optional and nothing is picked for you, so you confirm only the names you are sure of and leave the rest blank. A blank name is still saved with the award and can be linked any time later, and names it did not recognise can be linked here too.',
    'If the reader hits a file it cannot make sense of, it now says so clearly rather than throwing an error.',
  ],
}
