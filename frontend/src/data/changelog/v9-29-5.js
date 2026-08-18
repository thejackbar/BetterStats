export default {
  version: 'v9.29.5',
  date: '2026-08-18',
  sortKey: '2026-08-25T16:00:00Z',
  title: 'Sales Workspace: Extend Trial',
  items: [
    'A new Extend Trial button sits top right of the club detail pane\'s header — enabled for any club with a current or expired trial, disabled otherwise.',
    'Confirming asks the rep how many days to add (1-14, default 14), who to email the confirmation to (an existing contact or a new one), and, when the club has no Primary Admin yet, whether to make that contact one.',
    'An expired trial\'s start date resets to now; a still-active trial keeps its original start and just gets a later end. Either way every module the club holds on trial moves together.',
    'The confirmation email goes out on BetterAdmin → Comms → Templates\' "Sales rep trial extension" template, and the on-screen message reports the new end date plus whether the email actually sent.',
    'Nominating a Primary Admin either promotes an existing club co-admin, or invites a brand-new account the same way Club Users → Invite Admin does — set-your-own-password link included.',
  ],
}
