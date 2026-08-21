export default {
  version: 'v9.46.1',
  date: '2026-08-22',
  sortKey: '2026-08-22T10:00:00Z',
  title: 'Two voicemail follow-ups for a trial: one running down, one already over',
  items: [
    'Sales Workspace, Send an email: "Email following voicemail - offer to extend trial" is now "Email following voicemail. Trial already expired - offer to extend trial", and a new entry sits above it for a trial that is approaching expiry rather than one that has finished.',
    'The two read differently, because the two moments do. One says the trial finishes shortly and offers to extend it; the other says it has finished and offers to put it back on. Both leave a voicemail behind them and both send the club to the login page, since they already have an account.',
    'Both are editable in BetterAdmin → Comms → Templates. The existing row is renamed to say the trial has expired, unless a super admin has already renamed it themselves, in which case their own name stands.',
  ],
}
