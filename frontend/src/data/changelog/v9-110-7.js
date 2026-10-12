export default {
  version: 'v9.110.7',
  date: '2026-10-12',
  sortKey: '2026-10-12T20:00:00Z',
  title: 'Fantasy rounds lock at a set time, and late transfers wait for the next round',
  items: [
    'Each BetterFantasyCricket round now locks at a set time. After it, managers cannot change their XI, captain or chips until the round is scored. Until now the lock was midnight UTC, which is 11am in Melbourne, so a 9am game could still be changed after it started.',
    'The lock defaults to 9am on the first game day. Admins can change any round\'s lock time under Overview, Rounds, Locks, and it stays put when the rounds refresh from the draw.',
    'A transfer made after the lock is queued instead of refused. It happens once the round is scored, at the player prices then, and counts for the next round. Managers see their queued transfers on the Transfers screen and can cancel them.',
    'If a queued transfer can no longer happen, for example the budget does not stretch after the price changes, it is cancelled and the manager is told why. A captain who is transferred out hands the armband to the player coming in.',
  ],
}
