export default {
  version: 'v8.9.2.3',
  date: '2026-06-09',
  sortKey: '2026-06-09T23:45:00Z',
  title: 'Tidy duplicate partnership records & stop future pile-ups',
  items: [
    'Cleaned up hand-entered partnership records that now duplicate a synced scorecard partnership (the synced copy is kept). Records with no synced equivalent — older un-synced seasons — are left untouched.',
    'The partnership-records importer now skips any row that already exists, either as a synced scorecard partnership or as a record you imported before, so re-uploading a file can no longer pile up duplicates. The review screen shows how many rows were skipped and why.',
    'Fixed the importer’s duplicate check for summer seasons: it now matches on the season’s start year (e.g. 2016 for 2016/17) instead of the calendar year the game was played, which previously let January matches slip through as duplicates.',
  ],
}
