export default {
  version: 'v9.47.0',
  date: '2026-08-21',
  sortKey: '2026-08-22T23:00:00Z',
  title: 'A Backup settings page: the run time in Perth, how long backups are kept, and clearing old ones',
  items: [
    'Super Admin → Clubs & Data → Backup Settings is a screen of its own. It sets what time the daily backup runs and how many days of backups are kept, and lists what is actually stored on the server so old ones can be deleted.',
    'The backup time is Perth, Western Australian time all the way through now — the time you pick is the time that gets stored and the time the server checks against, rather than a UTC figure the screen converted back and forth. An existing schedule keeps the real-world time it already had.',
    'Retention is a plain number of days, so a club keeping 30 days of backups can drop to 7. Shortening the window does not delete anything when you save — the next run prunes what is then out of range, and the file list is there for freeing the space now.',
    'Stored backups can be selected and deleted, one or several at a time, with a running total of what that frees. "Select older than N days" picks the ones the next run would prune anyway. The most recent backup takes a second, separate confirmation, since it is the one a restore would use.',
    'Deleting removes the files only. The run stays on the Backups page with its sizes and per-club record counts, marked as having had its files removed, and stops offering a download or a restore that could not work.',
    'A backup that gets missed — the server was down at 3am, say — is now taken on the next check rather than skipped for the day, and the minute you set is honoured rather than only the hour.',
    'The backup fields have left General Settings, which now links across, so one screen decides what the schedule is.',
  ],
}
