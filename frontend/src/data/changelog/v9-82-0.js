export default {
  version: 'v9.82.0',
  date: '2026-09-18',
  // Above v9.81.0's sortKey, which origin/main has as the highest, or
  // SITE_VERSION never reaches this one. Check origin/main at merge time.
  sortKey: '2026-09-28T06:00:00Z',
  title: 'An operational area can involve several roles',
  items: [
    'In BetterAdmin → Setup → Areas & roles, an operational area now holds a set of roles rather than one. A Match Day area can list Umpires, Scorers and Team Managers together, and each role carries the qualification that gates it on its own — Umpires can need an accreditation while Scorers need nothing.',
    'Every shift is now for one of the area\'s roles. When you add a weekly pattern or a one-off shift, you pick the role it covers, and that role shows on the shift wherever it appears on the roster.',
    'Whether a shift counts as paid or volunteer now follows its role, so one area can mix paid and volunteer work. The qualification check and the "which roles are we short of" figures read the shift\'s own role too.',
    'Nothing changes for a club that already had single-role areas — each becomes a one-role set, and its existing shifts keep that role.',
  ],
}
