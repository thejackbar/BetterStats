export default {
  version: 'v8.43.6',
  date: '2026-06-29',
  sortKey: '2026-06-29T07:00:00Z',
  title: 'Twenty export: tolerate messy officer emails and phone numbers',
  items: [
    'Officers with a malformed email or phone number (a stray space, two numbers in one field, free text like "see website") no longer break the export. The bad value is cleaned or dropped, and a single problem officer is skipped and logged rather than taking down the whole club\'s export.',
  ],
}
