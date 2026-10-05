export default {
  version: 'v9.106.23',
  date: '2026-10-05',
  sortKey: '2026-10-05T12:00:00Z',
  title: 'Awards import now reads CSV files saved from Excel on a Mac, and says what went wrong when a file fails',
  items: [
    'A CSV saved from Excel on a Mac (or by some other tools) uses an old line ending that the import could not read. The page showed "Unexpected token I, Internal S... is not valid JSON" and nothing was added. These files now import normally.',
    'CSV files saved by Excel on Windows with curly quotes or accented letters now read correctly too.',
    'If an awards file still cannot be read, the page now shows a plain message and says nothing was added, instead of a JSON error.',
  ],
}
