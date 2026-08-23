export default {
  version: 'v9.23.2.4',
  date: '2026-08-14',
  sortKey: '2026-08-14T16:00:00Z',
  title: 'Manual stat adjustments, negative numbers wouldn’t stick',
  items: [
    'The spreadsheet-mode grid on Manual Entries → Adjustments reset a cell back to 0 the instant it read as unparsable, which included the moment right after typing a bare "-": so a negative adjustment could never be typed in, and clearing a "0" to type something new always bounced straight back.',
    'Cells now hold whatever you’re typing (a minus sign, a blank field, a trailing decimal point) until you click away, then normalise to a real number, so plus/minus adjustments work as intended.',
  ],
}
