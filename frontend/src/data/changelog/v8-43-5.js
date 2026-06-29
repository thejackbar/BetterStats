export default {
  version: 'v8.43.5',
  date: '2026-06-29',
  sortKey: '2026-06-29T06:00:00Z',
  title: 'Twenty export: customer billing fields and self-healing of deleted records',
  items: [
    'For clubs that are already customers, the export now fills in paid modules, subscription status, renewal date, billing cycle and annual value from the club\'s account, not just the prospect details.',
    'Deleting a record in the CRM no longer breaks the next export: it detects the record is gone and recreates it instead of erroring, so a club and its officers come through cleanly on a re-run.',
  ],
}
