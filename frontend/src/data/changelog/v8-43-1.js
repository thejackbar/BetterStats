export default {
  version: 'v8.43.1',
  date: '2026-06-29',
  sortKey: '2026-06-29T02:00:00Z',
  title: 'Export to Twenty: honour officer selection, add phone and role',
  items: [
    'The Twenty export now respects the per-officer outreach tick, so de-selected officers are skipped instead of all being exported.',
    'Officer mobile numbers now flow into the Twenty Phones field and their role into the Job title field. Associations now carry their short code and club count.',
    'The export only acts on clubs (not association rows) to match the filtered list, and a failure now returns a clear message with partial counts instead of a server error.',
  ],
}
