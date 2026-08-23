export default {
  version: 'v9.48.2.1',
  date: '2026-08-22',
  sortKey: '2026-08-22T21:00:00Z',
  title: 'A name in "Hand this follow-up to" or the sales-rep picker no longer lists twice',
  items: [
    "Sales Workspace's staff/rep pickers (\"Hand this follow-up to\" on Log a Call, and the super admin's owner filter/assignment picker) read every ClubMembership row directly, so a person holding two accounts under one display name showed up twice. Reported live with both Elton and Jack doubled in the follow-up picker.",
    'Both pickers now reuse the same fold the CRM owner filter already applies: accounts sharing a display name collapse into one entry, whichever account is picked.',
  ],
}
