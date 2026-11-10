export default {
  version: 'v9.142.7',
  date: '2026-11-10',
  // Above v9.142.6.3's sortKey (2026-11-19T15:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T16:00:00Z',
  title: 'Meta Ads HQ treats the 10 Nov restart as a new campaign',
  items: [
    "The restarted campaign now counts only what happened from 10 Nov 2026: trial signups, the signups table, the creative rows, converted, revenue and ROAS. A September registration no longer shows up under it.",
    "Meta's spend and the on-site funnel start from the same date, so cost per trial divides like with like, and you no longer need to set Reset from by hand.",
    "A line under the tiles says where counting starts and how many earlier registrations were left out, and how many carry no signup date. Nothing is dropped quietly.",
    "Manual plus and minus corrections made before the restart stay in the log, marked not counted, and are not in the total.",
    "An earlier registration is only left out of this campaign, never deleted. A manual counting-since date still never hides a registration, and it still wins if it is later than 10 Nov.",
  ],
}
