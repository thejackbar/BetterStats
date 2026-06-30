export default {
  version: 'v8.47.1',
  date: '2026-06-30',
  sortKey: '2026-06-30T16:00:00Z',
  title: 'Twenty export no longer times out',
  items: [
    'The "Export to Twenty" button now runs the export in the background instead of holding the request open. A big club list used to push past the server timeout and show a Gateway Time-out, even though the export was still running. The page now starts the job, shows progress, and reports the result when it finishes.',
    'You can leave the page while an export runs. Come back and it picks up where it was, then shows the final count.',
    'Only one export runs at a time, so a stuck or retried click can no longer stack overlapping runs that fought over Twenty\'s rate limit.',
  ],
}
