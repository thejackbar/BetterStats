export default {
  version: 'v8.43.3',
  date: '2026-06-29',
  sortKey: '2026-06-29T04:00:00Z',
  title: 'Twenty export: fix the error on clubs that had been contacted',
  items: [
    'Fixed an Internal Server Error when exporting clubs to the CRM. A contacted club was being sent an invalid lifecycle value, and the failure handler then masked the real cause, stopping the whole export. Both are fixed, so a single bad club is now skipped and logged while the rest export.',
  ],
}
