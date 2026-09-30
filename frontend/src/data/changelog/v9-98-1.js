export default {
  version: 'v9.98.1',
  date: '2026-10-04',
  // Above v9.98.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-04T13:00:00Z',
  title: 'A club that subscribed is no longer told its trial has ended',
  items: [
    'A club that trialled every module and then subscribed to some of them was told “Your BetterCricket trial has ended. Subscribe now to restore full access to your club’s stats and tools” once the other trials ran out. It still had its stats, so the message was wrong. A club paying for any module no longer sees the trial-ended banner or pop-up for the modules it chose not to add.',
    'While a paying club still has a module on trial, the banner names that module, for example “Your trial of BetterIQ ends in 4 days”, and offers to add it to the plan instead of warning about losing access.',
    'A club that has not subscribed to anything still sees the trial-ended notice as before, because it has lost access.',
  ],
}
